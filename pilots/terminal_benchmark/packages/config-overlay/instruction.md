# Repair configuration overlay resolution

Input is {"base":object,"overrides":object}. Recursively merge objects. An override value of null deletes that key if present and otherwise does nothing. Arrays replace existing arrays wholesale. Scalars including false, zero and empty string replace existing values. When an object replaces a non-object, merge it into an empty object, applying nested null deletion. Preserve base-only keys (including existing nulls). Do not concatenate arrays, ignore false-valued overrides or mutate inputs. Return {"config":merged_object}. Inputs always satisfy this shape.

Run `python /workspace/program.py INPUT.json OUTPUT.json`. Read one JSON document from the first path and write one JSON document to the second. Use only Python standard-library dependencies. Preserve the interface; do not edit or rely on evaluator tests.
