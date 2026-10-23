#!/bin/sh
set -eu
test -f partial.txt
printf 'qualified-result\n' > result.txt
