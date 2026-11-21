# Copyright 2013-2018 Therp BV <https://therp.nl>.
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
import logging

from odoo import _, api, fields, models

_logger = logging.getLogger(__name__)


class AttachMailManually(models.TransientModel):
    """Attach mail to selected documents."""

    _name = "fetchmail.attach.mail.manually"
    _description = __doc__

    name = fields.Char()
    folder_id = fields.Many2one(comodel_name="fetchmail.server.folder")
    mail_ids = fields.One2many(
        "fetchmail.attach.mail.manually.mail", "wizard_id", "Emails"
    )

    @api.model
    def _prepare_mail(self, folder, message_uid, mail_message):
        return {
            "message_uid": message_uid,
            "subject": mail_message.get("subject", ""),
            "date": mail_message.get("date") or False,
            "body": mail_message.get("body", ""),
            "email_from": mail_message.get("from", ""),
            "object_id": f"{folder.model_id.model},-1",
        }

    @api.model
    def default_get(self, fields_list):
        defaults = super().default_get(fields_list)
        if not fields_list or "name" in fields_list:
            defaults["name"] = _("Attach emails manually")
        defaults["mail_ids"] = []
        folder_model = self.env["fetchmail.server.folder"]
        folder_id = self.env.context.get("folder_id")
        defaults["folder_id"] = folder_id
        if not folder_id:
            return defaults
        folder = folder_model.browse(folder_id)
        connection = folder.server_id._connect__()
        criteria = "FLAGGED" if folder.flag_nonmatching else folder.get_criteria()
        message_uids = folder.get_message_uids(connection, criteria)
        for message_uid in message_uids[0].split():
            mail_message = folder._get_message_dict(
                folder.fetch_msg(connection, message_uid)
            )
            defaults["mail_ids"].append(
                (0, 0, self._prepare_mail(folder, message_uid, mail_message))
            )
        connection.close()
        return defaults

    def attach_mails(self):
        self.ensure_one()
        folder = self.folder_id
        server = folder.server_id
        # A line nobody chose is stored as `model,-1`, which reads back as a record
        # with a negative id: it is no choice.
        mails = self.mail_ids.filtered(
            lambda mail: mail.object_id and mail.object_id.id > 0
        )
        # All lines are checked before the first one is attached or the mailbox is
        # touched: one wrong line stops the wizard, not the lines after it.
        for mail in mails:
            folder._check_attach_target(mail.object_id)
        connection = server._connect__()
        folder._select_folder(connection)
        for mail in mails:
            message_uid = mail.message_uid
            mail_message = folder._get_message_dict(
                folder.fetch_msg(connection, message_uid)
            )
            folder.attach_mail(mail.object_id, mail_message)
            folder.update_msg(
                connection, message_uid, matched=True, flagged=folder.flag_nonmatching
            )
        connection.close()
        return {"type": "ir.actions.act_window_close"}


class AttachMailManuallyMail(models.TransientModel):
    """Attach single mail to selected documents."""

    _name = "fetchmail.attach.mail.manually.mail"
    _description = __doc__

    wizard_id = fields.Many2one("fetchmail.attach.mail.manually", readonly=True)
    message_uid = fields.Char("Message id", readonly=True)
    subject = fields.Char(readonly=True)
    date = fields.Datetime(readonly=True)
    email_from = fields.Char("From", readonly=True)
    body = fields.Html(readonly=True)
    object_id = fields.Reference(selection="_selection_object_id")

    @api.model
    def _selection_object_id(self):
        """The model of the folder the wizard was opened on; any model without one.

        Odoo evaluates this selection with the context of the request, which for the
        wizard carries `folder_id`, and refuses a value of a model outside it.
        """
        folder = self.env["fetchmail.server.folder"].browse(
            self.env.context.get("folder_id")
        )
        if folder:
            return [(folder.model_id.model, folder.model_id.name)]
        return [(m.model, m.name) for m in self.env["ir.model"].search([])]
