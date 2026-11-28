# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
import time

from odoo.exceptions import ValidationError

from .common import FOLDER, ImapCase


class TestPullLeavesMailbox(ImapCase):
    """What a pull does to a mailbox, read from a real IMAP server."""

    def _cron_pull(self):
        cron = self.env.ref("mail.ir_cron_mail_gateway_action")
        self.env["fetchmail.server"].with_context(
            cron_id=cron.id, cron_end_time=time.monotonic() + 120
        )._fetch_mails()

    def _assert_only_a_is_attached(self):
        message = self.attached("a")
        self.assertEqual((message.model, message.res_id), ("res.partner", self.payer.id))
        for suffix in ("b", "c"):
            self.assertFalse(self.attached(suffix), f"mail {suffix} was attached")
        inbox = self.env["mail.message"].search(
            [("message_id", "like", f"<{self.token}-in")]
        )
        self.assertFalse(inbox, "a mail of INBOX was taken")

    def test_button_pull_takes_the_folder_and_leaves_the_mailbox_as_it_was(self):
        server = self.make_server()
        self.make_folder(server)
        before = self.mailbox.state()
        server.fetch_mail()
        self.assertEqual(self.mailbox.state(), before)
        self._assert_only_a_is_attached()

    def test_scheduled_pull_takes_the_folder_and_leaves_the_mailbox_as_it_was(self):
        server = self.make_server()
        self.make_folder(server)
        before = self.mailbox.state()
        self._cron_pull()
        self.assertEqual(self.mailbox.state(), before)
        self._assert_only_a_is_attached()

    def test_mail_deleted_by_its_owner_is_still_there_after_a_pull(self):
        server = self.make_server()
        self.make_folder(server)
        server.fetch_mail()
        flags = self.mailbox.state()[FOLDER][2]
        self.assertEqual(flags.get("3"), ["\\Deleted"], "mail c is gone or its flags moved")

    def test_settings_that_write_do_what_they_are_told(self):
        """The other side: a folder set to mark and flag does mark and flag."""
        server = self.make_server()
        self.make_folder(server, seen="all", flag_nonmatching=True)
        server.fetch_mail()
        flags = self.mailbox.state()[FOLDER][2]
        self.assertEqual(flags["1"], ["\\Seen"])
        self.assertEqual(flags["2"], ["\\Flagged", "\\Seen"])

    def test_confirming_a_folder_leaves_the_mailbox_as_it_was(self):
        server = self.make_server()
        folder = self.make_folder(server, state="draft")
        before = self.mailbox.state()
        folder.button_confirm_folder()
        self.assertEqual(folder.state, "done")
        self.assertEqual(self.mailbox.state(), before)

    def test_confirming_a_folder_the_server_does_not_have_is_refused(self):
        server = self.make_server()
        folder = self.make_folder(server, path="No such folder", state="draft")
        with self.assertRaises(ValidationError):
            folder.button_confirm_folder()
        self.assertEqual(folder.state, "draft")

    def test_a_server_without_folders_only_keeps_the_pull_of_inbox(self):
        """The other side: a plain server is still pulled by Odoo, and its folders too."""
        server = self.make_server(folders_only=False)
        self.make_folder(server)
        server.fetch_mail()
        inbox = self.mailbox.state()["INBOX"][2]
        self.assertEqual(inbox, {"1": ["\\Seen"], "2": ["\\Seen"]})
        message = self.attached("a")
        self.assertEqual(message.res_id, self.payer.id)

    def test_folders_available_are_the_folders_of_the_server(self):
        server = self.make_server()
        self.assertEqual(
            set(server.folders_available.split("\n")), {"INBOX", FOLDER}
        )
