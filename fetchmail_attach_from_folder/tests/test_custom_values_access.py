# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
from odoo.exceptions import AccessError
from odoo.tests.common import TransactionCase, new_test_user


class TestCustomValuesAccess(TransactionCase):
    """Who may set what the record made from a mail gets.

    The values are applied when the fetch job makes the record, so the right to
    write them is the right to write a folder: administrators only
    (security/ir.access.csv). These tests need no IMAP server.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.plain = new_test_user(cls.env, login="folder_plain_user", groups="base.group_user")
        cls.admin = new_test_user(cls.env, login="folder_admin_user", groups="base.group_system")
        server = cls.env["fetchmail.server"].create(
            {
                "name": "access test",
                "server": "imap.invalid",
                "server_type": "imap",
                "user": "box",
                "password": "secret",
                "folders_only": True,
            }
        )
        cls.folder_values = {
            "server_id": server.id,
            "path": "INBOX",
            "model_id": cls.env.ref("base.model_res_partner").id,
            "model_field": "email",
            "match_algorithm": "odoo_standard",
            "mail_field": "from",
            "seen": "none",
            "flag_nonmatching": False,
            "delete_matching": False,
            "custom_values": "{'comment': 'set by an administrator'}",
        }
        cls.folder = cls.env["fetchmail.server.folder"].create(cls.folder_values)

    def test_a_user_without_the_system_group_cannot_change_the_values_of_a_folder(self):
        with self.assertRaises(AccessError):
            self.folder.with_user(self.plain).write({"custom_values": "{'comment': 'by a plain user'}"})
        self.assertEqual(self.folder.custom_values, "{'comment': 'set by an administrator'}")

    def test_a_user_without_the_system_group_cannot_make_a_folder_with_values(self):
        before = self.env["fetchmail.server.folder"].search_count([])
        with self.assertRaises(AccessError):
            self.env["fetchmail.server.folder"].with_user(self.plain).create(self.folder_values)
        self.assertEqual(self.env["fetchmail.server.folder"].search_count([]), before)

    def test_a_user_without_the_system_group_cannot_read_the_values_of_a_folder(self):
        with self.assertRaises(AccessError):
            self.folder.with_user(self.plain).custom_values  # noqa: B018

    def test_a_system_user_changes_the_values_of_a_folder(self):
        self.folder.with_user(self.admin).write({"custom_values": "{'comment': 'by another administrator'}"})
        self.assertEqual(self.folder.custom_values, "{'comment': 'by another administrator'}")
