In your fetchmail configuration, you'll find a new list field `Folders to 
monitor`. Add your folders here in IMAP notation (usually something like
`INBOX.your_folder_name.your_subfolder_name`), choose a model to attach mails
to and a matching algorithm to use.

Exact mailaddress
-----------------

Fill in a field to search for the email address in `Field (model)`. For
partners, this would be `email`. Also fill in the header field from the email
to look at in `Field (email)`. If you want to match incoming mails from your
customers, this would be `from`. You can also list header fields, so to match
partners receiving this email, you might fill in `to,cc,bcc`.

Domain of email addresses
-------------------------

Match the domain of the email address(es) found in `Field (email)`. This would
attach a mail to `test1@example.com` to a record with `Field (model)` set to
`test2@example.com`. Given that this is a fuzzy match, you probably want to
check `Use 1st match`, because otherwise nothing happens if multiple possible
matches are found.

Odoo standard
-------------

This is stricly speaking no matching algorithm, but calls the model's standard
action on new incoming mail, which is usually creating a new record.

`Custom Values` sets what that record gets: a Python dictionary of field names
and values, for example `{'move_type': 'in_invoice'}` on a folder whose target
model is `Journal Entry`, so that the mail becomes a vendor bill and not a journal
entry. It is read as a literal and never run; text that is no dictionary is
refused when the folder is saved. Left empty, the model's own defaults apply.
Other algorithms do not create a record and do not use it.

The record is made by the scheduled fetch action, not by the user who edited the
folder, and the values are applied as that action does. For this reason the field
is for administrators only: folders can be edited by the users of the group
`base.group_system` and by no one else.

A folder that changes nothing in the mailbox
--------------------------------------------

To read a folder of a mailbox that people use, so that nothing in it changes,
check `Process Only Specified Folders` on the server (its INBOX is then not
pulled by Odoo at all) and set the folder to `Mark email as seen`: `Never`,
`Flag Non-Matching Emails` off, `Delete Matched Emails` off and no
`Archive Folder`. A folder set like this is opened read-only: mail is read
without being marked as seen, flagged, moved or deleted, and mail that its
owner marked as deleted stays where it is. Any other setting writes to the
mailbox as it says, and the folder is then opened for writing.

A folder that is not read again and again
-----------------------------------------

A folder that changes nothing in the mailbox has no mark that tells a pull which
mail is new, so every pull reads the whole folder, downloads every mail and drops
the ones that are attached already. Check `Fetch New Mail Only` on the folder to
read only what came after the last pull: the folder remembers the UID where the
unbroken run of mail it took ends (`Last UID`) with the `UIDVALIDITY` the server
gave (`UIDVALIDITY`) and asks the server for the UIDs above it. When the server
gives another `UIDVALIDITY`, the UIDs mean other mail, and the folder is read as
usual once; mail that is attached already is not attached twice. A mail that
fails stops the run before it and is read again by the next pull. A mail that
always fails therefore holds the cursor, and the folder is read from that mail
on every pull, the mail after it too (it is not attached twice) until the mail is
dealt with: removed from the folder, or the cause of its failure removed. The
option is off by default, and `Attach Mail Manually` does not use it.

The scheduled action `Mail: Fetchmail Service` pulls the folders of every
confirmed server, and so does `Fetch Now` on the server.
