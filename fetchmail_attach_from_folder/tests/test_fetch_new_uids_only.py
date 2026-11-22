# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
import imaplib

from odoo.tools import mute_logger

from .common import FOLDER, ImapCase, raw_mail


class TestFetchNewUidsOnly(ImapCase):
    """A folder that remembers the last UID it looked at asks only for what is after it.

    The seed of ImapCase puts three mails in the folder: UID 1 (a, from the payer),
    UID 2 (b, a stranger's, read and starred) and UID 3 (c, marked \\Deleted by its
    owner, so never searched). What a pull asks the server is counted from the
    UID FETCH commands that go over the wire.
    """

    def setUp(self):
        super().setUp()
        self.fetches = []
        original = imaplib.IMAP4.uid
        fetches = self.fetches

        def spy(connection, command, *args):
            if command.lower() == "fetch":
                fetches.append(args[0])
            return original(connection, command, *args)

        self.patch(imaplib.IMAP4, "uid", spy)

    def _pull(self, folder):
        """One pull of the folder; the UIDs it fetched, as text."""
        self.fetches.clear()
        folder.server_id.fetch_mail()
        folder.invalidate_recordset()
        return [
            uid.decode() if isinstance(uid, bytes) else str(uid) for uid in self.fetches
        ]

    def _folder(self, **values):
        server = self.make_server()
        return self.make_folder(server, fetch_new_uids_only=True, **values)

    def test_nothing_new_fetches_nothing_and_the_mailbox_stays_as_it_was(self):
        folder = self._folder()
        before = self.mailbox.state()
        self.assertEqual(self._pull(folder), ["1", "2"])
        self.assertEqual(folder.last_uid, 2)
        self.assertEqual(folder.uid_validity, before[FOLDER][0])
        self.assertEqual(self._pull(folder), [])
        self.assertEqual(self._pull(folder), [])
        self.assertEqual(self.mailbox.state(), before)
        self.assertEqual(self.attached("a").res_id, self.payer.id)

    def test_a_new_mail_is_the_only_one_fetched(self):
        folder = self._folder()
        self._pull(folder)
        mail = raw_mail(self.payer.email, "Invoice 2", f"{self.token}-d")
        self.mailbox.put(FOLDER, mail)
        self.assertEqual(self._pull(folder), ["4"])
        self.assertEqual(folder.last_uid, 4)
        self.assertEqual(self.attached("d").res_id, self.payer.id)

    def test_the_last_mail_that_the_range_returns_is_not_fetched_again(self):
        """The server answers UID 5:* with UID 4 when nothing is newer than 4."""
        folder = self._folder()
        self._pull(folder)
        mail = raw_mail(self.payer.email, "Invoice 2", f"{self.token}-d")
        self.mailbox.put(FOLDER, mail)
        self._pull(folder)
        self.assertEqual(self._pull(folder), [])
        self.assertEqual(folder.last_uid, 4)

    def test_a_folder_made_again_is_read_from_its_start_without_doubles(self):
        folder = self._folder()
        self._pull(folder)
        old_validity = folder.uid_validity
        client = self.mailbox._client()
        try:
            client.delete(FOLDER)
        finally:
            client.logout()
        # the same mail as a (same Message-ID) and a new one, now under UIDs 1 and 2,
        # below the remembered last UID
        again = raw_mail(self.payer.email, "Invoice 1", f"{self.token}-a")
        self.mailbox.put(FOLDER, again)
        new = raw_mail(self.payer.email, "Invoice 3", f"{self.token}-e")
        self.mailbox.put(FOLDER, new)
        self.assertNotEqual(self.mailbox.state()[FOLDER][0], old_validity)
        self.assertEqual(self._pull(folder), ["1", "2"])
        self.assertEqual(self.attached("e").res_id, self.payer.id)
        self.assertEqual(len(self.attached("a")), 1)
        self.assertEqual(folder.uid_validity, self.mailbox.state()[FOLDER][0])
        self.assertEqual(folder.last_uid, 2)

    def test_without_the_flag_every_pull_reads_the_whole_folder(self):
        """The other side: a folder as it was in 18.0 is not changed by the fields."""
        folder = self.make_folder(self.make_server())
        self.assertEqual(self._pull(folder), ["1", "2"])
        self.assertEqual(self._pull(folder), ["1", "2"])
        self.assertFalse(folder.fetch_new_uids_only)
        self.assertEqual(folder.last_uid, 0)
        self.assertFalse(folder.uid_validity)

    def test_a_folder_that_marks_mail_is_searched_by_uid_too(self):
        folder = self._folder(seen="all", flag_nonmatching=True)
        self.assertEqual(self._pull(folder), ["1", "2"])
        self.assertEqual(self._pull(folder), [])
        flags = self.mailbox.state()[FOLDER][2]
        self.assertEqual(flags["1"], ["\\Seen"])
        self.assertEqual(flags["2"], ["\\Flagged", "\\Seen"])

    def test_the_manual_attach_wizard_still_lists_the_whole_folder(self):
        """The memory belongs to the pull; the wizard does not use it."""
        folder = self._folder()
        self._pull(folder)
        self.assertEqual(folder.last_uid, 2)
        connection = folder.server_id._connect__()
        try:
            uids = folder.get_message_uids(connection, folder.get_criteria())
        finally:
            connection.logout()
        self.assertEqual(uids[0].split(), [b"1", b"2"])

    def test_a_mail_that_failed_is_read_again_and_the_cursor_stops_before_it(self):
        """The mail of UID 2 fails in the middle of a pull; the ones after it pass."""
        folder = self._folder()
        for suffix in ("d", "e"):  # UIDs 4 and 5, from the payer
            mail = raw_mail(
                self.payer.email, f"Invoice {suffix}", f"{self.token}-{suffix}"
            )
            self.mailbox.put(FOLDER, mail)
        fail = {"on": True}
        original = type(folder).apply_matching

        def apply_matching(this, connection, message_uid):
            if fail["on"] and message_uid == b"2":
                raise ValueError("a mail that cannot be processed")
            return original(this, connection, message_uid)

        self.patch(type(folder), "apply_matching", apply_matching)
        logger = (
            "odoo.addons.fetchmail_attach_from_folder.models.fetchmail_server_folder"
        )
        with mute_logger(logger):
            self.assertEqual(self._pull(folder), ["1", "4", "5"])
        # the cursor stops after the last mail before the failed one
        self.assertEqual(folder.last_uid, 1)
        fail["on"] = False
        # the failed mail is read again, the one before it is not, and the ones
        # after it that were attached already are read but not attached twice
        self.assertEqual(self._pull(folder), ["2", "4", "5"])
        self.assertEqual(folder.last_uid, 5)
        for suffix in ("a", "d", "e"):
            self.assertEqual(len(self.attached(suffix)), 1, suffix)
        self.assertEqual(self._pull(folder), [])
