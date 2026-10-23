#!/bin/sh
set -eu
printf 'partial\n' > partial.txt
kill -TERM "$$"
