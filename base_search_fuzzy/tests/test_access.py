# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
from odoo.exceptions import AccessError

from odoo.addons.base.tests.common import BaseCommon


class TrgmIndexAccessCase(BaseCommon):
    # default _test_user_groups: every test runs as a plain internal user

    def test_internal_user_can_read_trgm_index(self):
        # 19.0 grants read on trgm.index to base.group_user
        self.assertGreaterEqual(self.env["trgm.index"].search_count([]), 0)

    def test_internal_user_cannot_create_trgm_index(self):
        field = self.env["ir.model.fields"].sudo().search(
            [("model", "=", "res.partner"), ("name", "=", "ref")], limit=1
        )
        with self.assertRaises(AccessError):
            self.env["trgm.index"].create({"field_id": field.id, "index_type": "gin"})
