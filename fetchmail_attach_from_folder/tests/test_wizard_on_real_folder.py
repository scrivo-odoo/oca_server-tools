# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
from .common import ImapCase


class TestWizardOnRealFolder(ImapCase):
    """The wizard that attaches mail by hand, on a folder of a real IMAP server."""

    def _wizard(self, folder):
        return self.env["fetchmail.attach.mail.manually"].with_context(
            folder_id=folder.id
        ).create({})

    def test_wizard_lists_the_mail_of_the_folder_and_leaves_the_mailbox_as_it_was(self):
        folder = self.make_folder(self.make_server())
        before = self.mailbox.state()
        wizard = self._wizard(folder)
        # c is marked \Deleted by its owner: the folder does not offer it.
        self.assertEqual(
            sorted(wizard.mail_ids.mapped("subject")), ["Hello", "Invoice 1"]
        )
        self.assertEqual(self.mailbox.state(), before)

    def test_wizard_attaches_only_the_mail_that_has_an_object(self):
        folder = self.make_folder(self.make_server())
        wizard = self._wizard(folder)
        before = self.mailbox.state()
        mail = wizard.mail_ids.filtered(lambda line: line.subject == "Invoice 1")
        mail.object_id = f"res.partner,{self.payer.id}"
        wizard.attach_mails()
        message = self.attached("a")
        self.assertEqual((message.model, message.res_id), ("res.partner", self.payer.id))
        self.assertFalse(self.attached("b"))
        self.assertEqual(self.mailbox.state(), before)

    def test_wizard_opened_without_a_folder_offers_nothing(self):
        wizard = self.env["fetchmail.attach.mail.manually"].create({})
        self.assertFalse(wizard.mail_ids)
