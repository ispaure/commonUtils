# Inspecting and editing SQLite databases

In a Qt file browser, right-click a local `.db`, `.db3`, `.sqlite` or `.sqlite3`
file and choose **Inspect SQLite…**. The inspector opens read-only. The host
decides which resources it can open and whether it can offer editing.

1. Choose a table or view. Open **Schema** to see its columns, declared types,
   defaults, primary-key order and generated or hidden columns.
2. In **Rows**, browse 100 records at a time with **Previous** and **Next**.
   To narrow the results, select a filter column, an operator and, where
   applicable, a value and its type. **Is NULL** and **Is not NULL** take no
   value. **Contains** and **Starts with** match literal, case-sensitive text.
3. Choose an optional sort column and direction, then select **Apply** to
   return to the first page with that filter and order. **Refresh** rereads the
   schema and rows. Each page uses the database contents at the time it loads.

## Save a batch of changes

1. Select **Enable editing** when available. Choose a row and **Edit row…** or
   **Stage delete**, or choose **Insert row…** to enter a new row. Views, virtual
   tables and tables without a declared primary key are read-only. Rows with a
   NULL key component cannot be updated or deleted.
2. Pick a SQLite value type when entering a field. **NULL** sets SQL NULL,
   **TEXT** preserves the entered characters, **INTEGER** takes a signed
   decimal whole number, **REAL** takes a finite decimal number, and **BLOB**
   takes hexadecimal byte pairs, such as `00 FF`. For inserts, **Use default**
   leaves the field to SQLite. The grid displays text in quotes so the text
   `'NULL'` is distinguishable from SQL `NULL`. SQLite applies the table's
   column affinity and constraints during save.
3. Select **Save changes** to commit the entire staged batch, or **Discard
   changes** to restore the displayed page. Table, page and query changes wait
   until you save or discard. Closing with staged changes offers **Save**,
   **Discard** and **Cancel**.

If SQLite rejects a save, the batch rolls back and the inspector keeps your
staged edits. Resolve a constraint error by revising the staged edits or
discarding the batch. If another writer holds the database lock, retry after
it finishes. If the original row or schema changed, discard the stale batch,
refresh and check the current values before editing again.

The rows grid previews long text and BLOBs. Each editable input accepts up to
65,536 characters, including the hexadecimal representation of a BLOB.
Existing fields beyond that limit stay unchanged when you edit the row.

[File browser](../file_browser/file_browser.md)
