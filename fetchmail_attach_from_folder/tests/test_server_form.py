# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
from lxml import etree

from odoo.tests.common import TransactionCase
from odoo.tools.safe_eval import safe_eval


class TestServerForm(TransactionCase):
    """What the form of an incoming server shows for each type of server.

    The conditions of the form are python expressions the browser evaluates; the
    test evaluates them the same way for each type and asks what a person sees.
    """

    def _what_is_seen(self, server_type):
        """(the page of folders is hidden, the target model is required)."""
        view = self.env["fetchmail.server"].get_view(view_type="form")
        arch = etree.fromstring(view["arch"])
        page = arch.xpath("//page[@string='Folders to monitor']")[0]
        target = arch.xpath("//field[@name='object_id']")[0]
        values = {"server_type": server_type}
        return (
            bool(safe_eval(page.get("invisible", "False"), values)),
            bool(safe_eval(target.get("required", "False"), values)),
        )

    def test_imap_server_shows_the_folders_and_needs_no_target_model(self):
        self.assertEqual(self._what_is_seen("imap"), (False, False))

    def test_gmail_server_shows_the_folders_and_needs_no_target_model(self):
        types = dict(self.env["fetchmail.server"]._fields["server_type"].selection)
        if "gmail" not in types:
            self.skipTest("google_gmail is not installed")
        self.assertEqual(self._what_is_seen("gmail"), (False, False))

    def test_pop_server_has_no_folders_and_needs_a_target_model(self):
        self.assertEqual(self._what_is_seen("pop"), (True, True))
