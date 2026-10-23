#!/bin/sh
set -eu
test -f result.txt
test "$(cat result.txt)" = 'qualified-result'
