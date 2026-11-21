# Copyright - 2013-2024 Therp BV <https://therp.nl>.
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
import logging
import re

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

list_response_pattern = re.compile(
    r'\((?P<flags>.*?)\) "(?P<delimiter>.*)" (?P<name>.*)'
)


class FetchmailServer(models.Model):
    _inherit = "fetchmail.server"

    def _compute_folders_available(self):
        """Retrieve available folders from IMAP server."""

        def parse_list_response(line):
            string_line = line.decode("utf-8")
            flags, delimiter, mailbox_name = list_response_pattern.match(
                string_line
            ).groups()
            mailbox_name = mailbox_name.strip('"')
            return (flags, delimiter, mailbox_name)

        for this in self:
            if this.state != "done":
                this.folders_available = _("Confirm connection first.")
                continue
            try:
                connection = this._connect__()
            except UserError:
                this.folders_available = _("Confirm connection first.")
                continue
            list_result = connection.list()
            if list_result[0] != "OK":
                this.folders_available = _("Unable to retrieve folders.")
                continue
            folders_available = []
            for folder_entry in list_result[1]:
                folders_available.append(parse_list_response(folder_entry)[2])
            this.folders_available = "\n".join(folders_available)
            connection.logout()

    folders_available = fields.Text(
        string="Available folders",
        compute="_compute_folders_available",
    )
    folder_ids = fields.One2many(
        comodel_name="fetchmail.server.folder",
        inverse_name="server_id",
        string="Folders",
        context={"active_test": False},
    )
    folders_only = fields.Boolean(
        string="Process Only Specified Folders",
        help="Enable this option to ignore the default IMAP inbox processing and "
        "retrieve emails only from the specified folders.",
    )
    # Below existing fields, that are modified by this module.
    object_id = fields.Many2one(required=False)  # comodel_name='ir.model'
    server_type = fields.Selection(default="imap")

    @api.onchange("server_type", "is_ssl", "object_id")
    def onchange_server_type(self):
        result = super().onchange_server_type()
        self.state = "draft"
        return result

    def _fetch_mail(self, batch_limit=50):
        """Pull the INBOX of the servers Odoo pulls and the folders of every server.

        A server marked "folders only" is not handed to Odoo at all: its INBOX is
        neither read nor marked as seen and none of its mail is routed. The scheduled
        pull and the button of the server both come through here.
        """
        folders_only = self.filtered("folders_only")
        plain = self - folders_only
        result_exception = None
        if plain:
            result_exception = super(FetchmailServer, plain)._fetch_mail(
                batch_limit=batch_limit
            )
        for server in self:
            server.folder_ids.fetch_mail()
        folders_only.with_context(fetchmail_cron_running=True).write(
            {"date": fields.Datetime.now()}
        )
        return result_exception
