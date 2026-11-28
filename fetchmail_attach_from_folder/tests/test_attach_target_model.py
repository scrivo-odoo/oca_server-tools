# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
"""A mail is attached only to a record of the model of its folder.

The folder says which model it attaches mail to; the record a person picks in the
wizard carries its own model. Before the check, the folder's model was joined to the
id of the picked record: a partner picked on a folder of channels put the mail on the
channel with the partner's number.
"""

import uuid

from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase

from .common import ImapCase, raw_mail

WIZARD = "fetchmail.attach.mail.manually"
LINE = "fetchmail.attach.mail.manually.mail"


class TestAttachMailTargetModel(TransactionCase):
    """attach_mail, which every caller goes through, wizard or pull."""

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
            }
        )
        cls.folder = cls.env["fetchmail.server.folder"].create(
            {
                "server_id": cls.server.id,
                "path": "INBOX",
                "model_id": cls.env.ref("base.model_res_partner").id,
                "model_field": "email",
                "match_algorithm": "email_exact",
                "mail_field": "from",
            }
        )
        cls.partner = cls.env["res.partner"].create({"name": "Payer"})
        cls.channel = cls.env["discuss.channel"].create(
            {"name": "A channel", "channel_type": "channel"}
        )

    def _mail(self):
        token = uuid.uuid4().hex[:12]
        message_dict = self.folder._get_message_dict(
            raw_mail("payer@example.test", "Invoice", token)
        )
        return token, message_dict

    def _attached(self, token):
        return self.env["mail.message"].search(
            [("message_id", "=", f"<{token}@example.test>")]
        )

    def test_record_of_the_folder_model_gets_the_mail(self):
        token, message_dict = self._mail()
        self.folder.attach_mail(self.partner, message_dict)
        message = self._attached(token)
        self.assertEqual((message.model, message.res_id), ("res.partner", self.partner.id))

    def test_record_of_another_model_is_refused_and_nothing_is_written(self):
        token, message_dict = self._mail()
        with self.assertRaises(UserError) as caught:
            self.folder.attach_mail(self.channel, message_dict)
        # The refusal says which two models disagree.
        self.assertIn("discuss.channel", caught.exception.args[0])
        self.assertIn("res.partner", caught.exception.args[0])
        self.assertFalse(self._attached(token))

    def test_wizard_offers_only_the_model_of_its_folder(self):
        offered = (
            self.env[LINE]
            .with_context(folder_id=self.folder.id)
            .fields_get(["object_id"])["object_id"]["selection"]
        )
        self.assertEqual([model for model, _ in offered], ["res.partner"])

    def test_wizard_opened_without_a_folder_offers_every_model(self):
        offered = self.env[LINE].fields_get(["object_id"])["object_id"]["selection"]
        models = [model for model, _ in offered]
        self.assertIn("res.partner", models)
        self.assertIn("discuss.channel", models)


class TestWizardTargetModelOnRealFolder(ImapCase):
    """The wizard on a folder of a real IMAP server, the folder takes channels."""

    def setUp(self):
        super().setUp()
        self.channel = self.env["discuss.channel"].create(
            {"name": f"Channel {self.token}", "channel_type": "channel"}
        )

    def _folder_of_channels(self, **values):
        return self.make_folder(
            self.make_server(),
            model_id=self.env["ir.model"]._get_id("discuss.channel"),
            model_field="name",
            mail_field="subject",
            **values,
        )

    def _wizard(self, folder):
        return self.env[WIZARD].with_context(folder_id=folder.id).create({})

    @staticmethod
    def _line(wizard, subject):
        return wizard.mail_ids.filtered(lambda line: line.subject == subject)

    def test_channel_picked_on_a_folder_of_channels_gets_the_mail(self):
        folder = self._folder_of_channels()
        wizard = self._wizard(folder)
        self._line(wizard, "Invoice 1").object_id = f"discuss.channel,{self.channel.id}"
        before = self.mailbox.state()
        wizard.attach_mails()
        message = self.attached("a")
        self.assertEqual(
            (message.model, message.res_id), ("discuss.channel", self.channel.id)
        )
        self.assertEqual(self.mailbox.state(), before)

    def test_partner_cannot_be_picked_on_a_folder_of_channels(self):
        """In the context of the wizard the choice itself is refused."""
        folder = self._folder_of_channels()
        wizard = self._wizard(folder)
        line = self._line(wizard, "Invoice 1")
        before = self.mailbox.state()
        with self.assertRaises((ValueError, UserError)):
            line.object_id = f"res.partner,{self.payer.id}"
        self.assertNotEqual(line.object_id, self.payer)
        self.assertEqual(self.mailbox.state(), before)

    def test_partner_set_outside_the_wizard_context_is_refused_when_attaching(self):
        """A value written by a caller that does not carry the folder, as an RPC may."""
        folder = self._folder_of_channels()
        wizard = self._wizard(folder)
        line = self._line(wizard, "Invoice 1")
        line.with_context(folder_id=False).object_id = f"res.partner,{self.payer.id}"
        before = self.mailbox.state()
        with self.assertRaises(UserError):
            wizard.attach_mails()
        self.assertFalse(self.attached("a"))
        self.assertEqual(self.mailbox.state(), before)

    def test_one_wrong_line_stops_the_whole_wizard_before_the_mailbox_is_touched(self):
        """The good line first, the wrong one second, on a folder that marks mail as seen."""
        folder = self._folder_of_channels(seen="all")
        wizard = self._wizard(folder)
        self._line(wizard, "Invoice 1").object_id = f"discuss.channel,{self.channel.id}"
        wrong = self._line(wizard, "Hello")
        wrong.with_context(folder_id=False).object_id = f"res.partner,{self.payer.id}"
        # Opening the wizard on a folder that writes has closed it once: the state to
        # compare with is the one after that.
        before = self.mailbox.state()
        with self.assertRaises(UserError):
            wizard.attach_mails()
        self.assertFalse(self.attached("a"))
        self.assertFalse(self.attached("b"))
        self.assertEqual(self.mailbox.state(), before)

    def test_lines_nobody_chose_attach_nothing_when_read_again_from_the_database(self):
        """A line is stored with `model,-1` until a record is chosen: no record."""
        folder = self._folder_of_channels()
        wizard = self._wizard(folder)
        self._line(wizard, "Invoice 1").object_id = f"discuss.channel,{self.channel.id}"
        self.env.invalidate_all()
        before = self.mailbox.state()
        wizard.attach_mails()
        message = self.attached("a")
        self.assertEqual(
            (message.model, message.res_id), ("discuss.channel", self.channel.id)
        )
        self.assertFalse(self.attached("b"))
        self.assertEqual(self.mailbox.state(), before)
