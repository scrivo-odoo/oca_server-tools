# Copyright - 2015-2026 Therp BV <https://therp.nl>.
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
# pylint: disable=method-required-super
from unittest.mock import MagicMock, patch

from odoo.tests.common import TransactionCase


class TestAttachMailManually(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Wizard = cls.env["fetchmail.attach.mail.manually"]
        cls.Folder = cls.env["fetchmail.server.folder"]
        cls.Partner = cls.env["res.partner"]
        cls.server = cls.env["fetchmail.server"].create(
            {
                "name": "Test IMAP",
                "server": "imap.example.com",
                "server_type": "imap",
                "user": "test@example.com",
                "password": "secret",
                "state": "done",
            }
        )
        cls.folder = cls.Folder.create(
            {
                "server_id": cls.server.id,
                "sequence": 5,
                "path": "INBOX",
                "model_id": cls.env.ref("base.model_res_partner").id,
                "model_field": "email",
                "match_algorithm": "email_exact",
                # The intention is to link email to sender partner object.
                "mail_field": "from",
            }
        )
        cls.partner = cls.Partner.create(
            {"name": "Test Partner", "email": "test@example.com"}
        )

    def _mock_connection(self):
        mock_conn = MagicMock()
        mock_conn.select.return_value = ("OK",)
        mock_conn.search.return_value = ("OK", [b"1"])
        mock_conn.uid.return_value = ("OK", [b"1"])
        mock_conn.fetch.return_value = (
            "OK",
            [(b"1 (RFC822 {123}", b"Mocked raw email content")],
        )
        mock_conn.list.return_value = (
            "OK",
            [b'(\\HasNoChildren) "." "INBOX"', b'(\\HasChildren) "." "Sent"'],
        )
        return mock_conn

    def test_prepare_mail_returns_expected_dict(self):
        """Test _prepare_mail returns correct structure."""
        folder = self.folder
        message_uid = "123"
        mail_message = {
            "subject": "Test",
            "date": "2025-07-23",
            "from": "test@example.com",
            "body": "<p>Body</p>",
        }
        result = self.Wizard._prepare_mail(folder, message_uid, mail_message)
        expected = {
            "message_uid": "123",
            "subject": "Test",
            "date": "2025-07-23",
            "body": "<p>Body</p>",
            "email_from": "test@example.com",
            "object_id": "res.partner,-1",
        }
        self.assertEqual(result, expected)

    def test_wizard_name_is_translated(self):
        """Test that default name is translated."""
        wizard = self.Wizard.create({})
        self.assertEqual(wizard.name, "Attach emails manually")

    def test_compute_folders_available_success(self):
        """You must return the available folders."""
        with patch.object(
            self.server.__class__, "_connect__", return_value=self._mock_connection()
        ):
            result = self.server.folders_available
            self.assertEqual(result, "INBOX\nSent")

    def test_compute_folders_available_not_done(self):
        """If the server is not confirmed, you must warn."""
        self.server.state = "draft"
        result = self.server.folders_available
        self.assertEqual(result, "Confirm connection first.")

    def test_compute_folders_available_list_error(self):
        """If list() fails, it should display an error message."""
        mock_conn = MagicMock()
        mock_conn.list.return_value = ("NO", [])
        with patch.object(self.server.__class__, "_connect__", return_value=mock_conn):
            result = self.server.folders_available
            self.assertEqual(result, "Unable to retrieve folders.")
