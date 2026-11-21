# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
"""What a pull and the wizard send to the server, checked without a server.

The tests on a real IMAP server (common.py) read the state of the mailbox before and
after, and are skipped where no such server runs. These read the commands instead:
the connection is a stand-in that answers like a one-message folder and writes down
every call. They run everywhere, and they see a folder opened for writing, a flag
set, a copy or an expunge sent for a folder whose settings change nothing.

What they do not see is the server's side of a command: that a folder opened with
EXAMINE has nothing for CLOSE to delete is shown only by the real-server tests.
"""

from unittest.mock import patch

from odoo.tests.common import TransactionCase

from .common import raw_mail

READING = {
    ("select",),
    ("uid", "search"),
    ("uid", "fetch"),
    ("close",),
    ("logout",),
}
WRITING_UID = {"store", "copy"}


class RecordingConnection:
    """An IMAP connection with one message in its folder, that records every call."""

    def __init__(self, raw):
        self.raw = raw
        self.calls = []

    def select(self, mailbox="INBOX", readonly=False):
        self.calls.append(("select", mailbox, readonly))
        return ("OK", [b"1"])

    def uid(self, command, *args):
        command = command.lower()
        self.calls.append(("uid", command) + args)
        if command == "search":
            return ("OK", [b"1"])
        if command == "fetch":
            return ("OK", [(b"1 (BODY[] {%d}" % len(self.raw), self.raw)])
        return ("OK", [b""])

    def __getattr__(self, name):
        # close, logout, expunge, create, append, delete, ...: written down, answered OK.
        def call(*args):
            self.calls.append((name,) + args)
            return ("OK", [b""])

        return call

    def commands(self):
        return {
            call[:2] if call[0] == "uid" else call[:1] for call in self.calls
        }

    def reads_only(self):
        """No command outside READING was sent, and every folder was opened read-only."""
        selects = [call for call in self.calls if call[0] == "select"]
        return (
            self.commands() <= READING
            and bool(selects)
            and all(call[2] for call in selects)
        )


class TestMailboxCommands(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.server = cls.env["fetchmail.server"].create(
            {
                "name": "Test IMAP",
                "server": "imap.example.com",
                "server_type": "imap",
                "user": "test@example.com",
                "password": "secret",
                "state": "done",
                "folders_only": True,
            }
        )
        cls.payer = cls.env["res.partner"].create(
            {"name": "Payer", "email": "payer@example.test"}
        )

    def _folder(self, **values):
        vals = {
            "server_id": self.server.id,
            "path": "Invoices",
            "model_id": self.env.ref("base.model_res_partner").id,
            "model_field": "email",
            "match_algorithm": "email_exact",
            "mail_field": "from",
            "seen": "none",
            "flag_nonmatching": False,
            "delete_matching": False,
            "state": "done",
        }
        vals.update(values)
        return self.env["fetchmail.server.folder"].create(vals)

    def _connection(self, token, sender="payer@example.test"):
        return RecordingConnection(raw_mail(sender, "Invoice", token))

    def _connected(self, connection):
        return patch.object(
            type(self.server), "_connect__", return_value=connection
        )

    def test_pull_of_a_folder_that_changes_nothing_sends_only_reading_commands(self):
        folder = self._folder()
        connection = self._connection("pull-quiet")
        with self._connected(connection):
            folder.fetch_mail()
        # The pull ran to the end: it searched, fetched and attached the mail.
        self.assertLessEqual({("uid", "search"), ("uid", "fetch")}, connection.commands())
        self.assertTrue(
            self.env["mail.message"].search(
                [("message_id", "=", "<pull-quiet@example.test>")]
            )
        )
        self.assertTrue(connection.reads_only(), connection.calls)
        # BODY.PEEK[] does not set \Seen, RFC822 does.
        fetch = [call for call in connection.calls if call[:2] == ("uid", "fetch")]
        self.assertEqual({call[-1] for call in fetch}, {"(BODY.PEEK[])"})

    def test_pull_of_a_folder_that_marks_mail_sends_the_marks(self):
        """The other side: the stand-in does see a write when the settings ask for one."""
        folder = self._folder(seen="all")
        connection = self._connection("pull-marking")
        with self._connected(connection):
            folder.fetch_mail()
        stores = [call for call in connection.calls if call[:2] == ("uid", "store")]
        self.assertEqual([call[2:] for call in stores], [(b"1", "+FLAGS", "\\Seen")])
        self.assertFalse(connection.reads_only())
        self.assertFalse([call for call in connection.calls if call[0] == "select"][0][2])

    def test_pull_of_a_folder_that_archives_sends_copy_and_expunge(self):
        folder = self._folder(archive_path="Archive")
        connection = self._connection("pull-archiving")
        with self._connected(connection):
            folder.fetch_mail()
        commands = connection.commands()
        self.assertIn(("uid", "copy"), commands)
        self.assertIn(("expunge",), commands)

    def test_wizard_on_a_folder_that_changes_nothing_sends_only_reading_commands(self):
        folder = self._folder()
        connection = self._connection("wizard-quiet")
        with self._connected(connection):
            wizard = self.env["fetchmail.attach.mail.manually"].with_context(
                folder_id=folder.id
            ).create({})
            wizard.mail_ids.object_id = f"res.partner,{self.payer.id}"
            wizard.attach_mails()
        self.assertEqual(len(wizard.mail_ids), 1)
        self.assertTrue(
            self.env["mail.message"].search(
                [("message_id", "=", "<wizard-quiet@example.test>")]
            )
        )
        self.assertTrue(connection.reads_only(), connection.calls)
