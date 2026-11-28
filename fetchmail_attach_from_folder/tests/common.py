# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
"""Tests of what a pull does to a mailbox, on a real IMAP server.

The state of a mailbox is read from the server, not from a mock: for every folder
its UIDVALIDITY, its UIDNEXT and the flags of every message. The server is any IMAP
server that takes plain-text logins and gives every user name its own empty mailbox
(dovecot with a static password does). Where it is: FETCHMAIL_TEST_IMAP_HOST,
FETCHMAIL_TEST_IMAP_PORT, FETCHMAIL_TEST_IMAP_PASSWORD. Without a server on that
address the tests that need it are skipped, and the skip names the address.
"""

import imaplib
import os
import re
import socket
import unittest
import uuid

from odoo.tests.common import TransactionCase

IMAP_HOST = os.environ.get("FETCHMAIL_TEST_IMAP_HOST", "fetchmail-test-imap")
IMAP_PORT = int(os.environ.get("FETCHMAIL_TEST_IMAP_PORT", "31143"))
IMAP_PASSWORD = os.environ.get("FETCHMAIL_TEST_IMAP_PASSWORD", "testpass")

FOLDER = "Invoices"
LIST_LINE = re.compile(r'\((?P<flags>.*?)\) "(?P<delimiter>.*)" (?P<name>.*)')


def imap_reachable():
    try:
        with socket.create_connection((IMAP_HOST, IMAP_PORT), timeout=3):
            return True
    except OSError:
        return False


def raw_mail(sender, subject, token, body="body"):
    return (
        f"From: {sender}\r\nTo: books@example.test\r\nSubject: {subject}\r\n"
        f"Message-ID: <{token}@example.test>\r\n"
        "Date: Sat, 21 Nov 2026 10:00:00 +0000\r\n"
        f"Content-Type: text/plain; charset=utf-8\r\n\r\n{body}\r\n"
    ).encode()


class Mailbox:
    """One user of the test IMAP server: puts mail in, reads the state of every folder."""

    def __init__(self, user):
        self.user = user

    def _client(self):
        client = imaplib.IMAP4(IMAP_HOST, IMAP_PORT, timeout=20)
        client.login(self.user, IMAP_PASSWORD)
        return client

    def put(self, folder, raw, flags=""):
        client = self._client()
        try:
            if folder != "INBOX":
                client.create(folder)  # a folder that is there answers NO: fine
            typ, data = client.append(folder, f"({flags})" if flags else None, None, raw)
            assert typ == "OK", data
        finally:
            client.logout()

    def state(self):
        """{folder: (UIDVALIDITY, UIDNEXT, {uid: sorted flags})} of every folder.

        Read with EXAMINE and STATUS, which change nothing. \\Recent is left out: the
        server sets it by itself for the first session that sees a message.
        """
        client = self._client()
        try:
            _typ, listing = client.list()
            names = sorted(
                LIST_LINE.match(line.decode()).group("name").strip('"')
                for line in listing
            )
            state = {}
            for name in names:
                _typ, data = client.status(name, "(MESSAGES UIDNEXT UIDVALIDITY)")
                numbers = dict(
                    re.findall(r"(MESSAGES|UIDNEXT|UIDVALIDITY) (\d+)", data[0].decode())
                )
                flags = {}
                if int(numbers["MESSAGES"]):
                    client.select(name, readonly=True)
                    _typ, rows = client.uid("fetch", "1:*", "(FLAGS)")
                    for row in rows:
                        text = row.decode()
                        uid = re.search(r"UID (\d+)", text).group(1)
                        found = re.search(r"FLAGS \(([^)]*)\)", text).group(1).split()
                        flags[uid] = sorted(flag for flag in found if flag != "\\Recent")
                state[name] = (numbers["UIDVALIDITY"], numbers["UIDNEXT"], flags)
            return state
        finally:
            client.logout()


class ImapCase(TransactionCase):
    """A fresh mailbox for every test, seeded the same way.

    INBOX holds two mails (one from the partner, one from a stranger). The folder
    holds three: a, from the partner; b, from a stranger, already read and starred
    by its owner; c, from the partner, marked \\Deleted by its owner.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        if not imap_reachable():
            raise unittest.SkipTest(f"no test IMAP server at {IMAP_HOST}:{IMAP_PORT}")

    def setUp(self):
        super().setUp()
        # The pull of Odoo commits after every server and rolls back after a mail it
        # could not process, which the cursor of a test forbids. Only the commit and
        # the rollback are replaced; the pull, its connection and its mailbox are real.
        self.patch(self.cr, "commit", lambda: None)
        self.patch(self.cr, "rollback", lambda: None)
        self.token = uuid.uuid4().hex[:12]
        self.mailbox = Mailbox(f"box-{self.token}")
        self.payer = self.env["res.partner"].create(
            {"name": "Payer", "email": f"payer-{self.token}@example.test"}
        )
        token = self.token
        self.mailbox.put("INBOX", raw_mail(self.payer.email, "Inbox payer", f"{token}-in1"))
        self.mailbox.put(
            "INBOX", raw_mail("stranger@example.test", "Inbox stranger", f"{token}-in2")
        )
        self.mailbox.put(FOLDER, raw_mail(self.payer.email, "Invoice 1", f"{token}-a"))
        self.mailbox.put(
            FOLDER,
            raw_mail("stranger@example.test", "Hello", f"{token}-b"),
            "\\Seen \\Flagged",
        )
        self.mailbox.put(
            FOLDER,
            raw_mail(self.payer.email, "Deleted by its owner", f"{token}-c"),
            "\\Deleted",
        )

    def make_server(self, **values):
        vals = {
            "name": f"test imap {self.token}",
            "server": IMAP_HOST,
            "port": IMAP_PORT,
            "is_ssl": False,
            "server_type": "imap",
            "user": self.mailbox.user,
            "password": IMAP_PASSWORD,
            "state": "done",
            "folders_only": True,
        }
        vals.update(values)
        return self.env["fetchmail.server"].create(vals)

    def make_folder(self, server, path=FOLDER, **values):
        """A folder that changes nothing in the mailbox: no flags, no archive, no delete."""
        vals = {
            "server_id": server.id,
            "path": path,
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

    def attached(self, suffix):
        """The mail.message made from the mail seeded under this suffix, if any."""
        return self.env["mail.message"].search(
            [("message_id", "=", f"<{self.token}-{suffix}@example.test>")]
        )
