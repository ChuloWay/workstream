# Repair the file inventory tool

Input is {"root":"relative-directory"}. The evaluator creates a tree of regular files/directories beneath this root, without links. Recursively inventory every regular file except files whose basename ends with the case-sensitive suffix .tmp. A directory ending in .tmp is still traversed. Return {"files":[{"path":relative_POSIX_path,"bytes":byte_count,"sha256":lowercase_SHA256},...]}, sorted lexicographically by path. Hash exact bytes, not decoded characters. Include empty files; an empty directory gives an empty list. The input root is always a valid directory beneath the current working directory; handling hostile roots or symlinks is not this exercise's contract.

Run `python /workspace/program.py INPUT.json OUTPUT.json`. Read one JSON document from the first path and write one JSON document to the second. Use only Python standard-library dependencies. Preserve the interface; do not edit or rely on evaluator tests.
