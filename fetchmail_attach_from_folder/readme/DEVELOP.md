A matching algorithm of your own is added in a module that depends on this one,
without a change to it. Add a value to `match_algorithm` and answer it in
`_get_algorithm`, with an object that has `search_matches(folder, message_dict)`
and returns the records the mail belongs to:

.. code-block:: python

    class FetchmailServerFolder(models.Model):
        _inherit = "fetchmail.server.folder"

        match_algorithm = fields.Selection(
            selection_add=[("my_rule", "My rule")],
            ondelete={"my_rule": "cascade"},
        )

        def _get_algorithm(self):
            self.ensure_one()
            if self.match_algorithm == "my_rule":
                return MyRule()
            return super()._get_algorithm()

The tests of this module read a real IMAP server: see `tests/common.py` for
where they look for it. Without one they are skipped.
