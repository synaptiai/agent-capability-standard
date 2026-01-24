# Capability IO spec

Every capability defines input_schema and output_schema.

Workflow composition rule:
- A step may only consume fields that exist in prior step outputs.
- If required fields are missing, insert the missing capability or request user input.
