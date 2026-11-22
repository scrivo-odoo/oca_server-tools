# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
from odoo.exceptions import ValidationError

from .common import ImapCase


class TestCustomValues(ImapCase):
    """A folder in "Odoo Standard" mode can say what the record made from a mail gets.

    The target is res.partner: a mail makes a partner named after its subject, and
    the folder's values (here `comment`, a field that no mail sets) are on it. The
    seed of ImapCase puts two searched mails in the folder: "Invoice 1" and "Hello".
    """

    def _pull(self, **values):
        folder = self.make_folder(
            self.make_server(), match_algorithm="odoo_standard", **values
        )
        folder.server_id.fetch_mail()
        return folder

    def _made(self, subject):
        return self.env["res.partner"].search([("name", "=", subject)])

    def test_values_of_the_folder_are_on_the_record_made_from_a_mail(self):
        self._pull(custom_values="{'comment': 'made by the folder', 'ref': 'F-1'}")
        for subject in ("Invoice 1", "Hello"):
            made = self._made(subject)
            self.assertEqual(len(made), 1, subject)
            self.assertEqual(made.comment, "<p>made by the folder</p>", subject)
            self.assertEqual(made.ref, "F-1", subject)

    def test_a_folder_without_values_makes_the_record_as_before(self):
        self._pull()
        made = self._made("Invoice 1")
        self.assertEqual(len(made), 1)
        self.assertFalse(made.comment)
        self.assertFalse(made.ref)

    def test_a_blank_value_is_no_value(self):
        self._pull(custom_values="  \n ")
        made = self._made("Invoice 1")
        self.assertEqual(len(made), 1)
        self.assertFalse(made.comment)

    def test_another_algorithm_does_not_use_the_values(self):
        """email_exact attaches to the existing partner and makes nothing."""
        folder = self.make_folder(
            self.make_server(), custom_values="{'comment': 'made by the folder'}"
        )
        folder.server_id.fetch_mail()
        self.assertFalse(self._made("Invoice 1"))
        self.assertFalse(self.payer.comment)
        self.assertEqual(self.attached("a").res_id, self.payer.id)

    def test_values_of_other_types_than_text_reach_the_record(self):
        self._pull(custom_values="{'color': 3, 'employee': True, 'ref': None}")
        made = self._made("Invoice 1")
        self.assertEqual(len(made), 1)
        self.assertEqual(made.color, 3)
        self.assertTrue(made.employee)

    def test_values_that_are_no_dictionary_are_refused_with_a_message(self):
        server = self.make_server()
        for text in (
            "not a dict",
            "[1, 2]",
            "{1: 2}",
            "{'a': __import__('os')}",
            "{'a': }",
            "'comment'",
        ):
            with self.subTest(text=text):
                with self.assertRaises(ValidationError) as caught:
                    self.make_folder(
                        server, match_algorithm="odoo_standard", custom_values=text
                    )
                self.assertIn("dictionary", str(caught.exception))

    def test_a_good_text_turned_bad_on_write_is_refused_too(self):
        folder = self.make_folder(
            self.make_server(),
            match_algorithm="odoo_standard",
            custom_values="{'comment': 'x'}",
        )
        with self.assertRaises(ValidationError):
            folder.write({"custom_values": "[1]"})
