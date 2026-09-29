#!/usr/bin/env bash

set -euo pipefail

cd /src/fluent-bit

# Install dependencies
apt-get update
apt-get install -y cmake make flex bison pkg-config libssl-dev libyaml-dev gcc g++ gcovr

unset CFLAGS CXXFLAGS LDFLAGS

# We modify the expiration date of the Fluent Bit AWS credentials so that
# the test considers them as valid
sed -i -e 's/2025-10-24T/3025-10-24T/' -e 's/2025-11-09T/3025-11-09T/' \
  tests/internal/aws_credentials_{http,sts}.c

rm -rf build
cmake -S . -B build -DFLB_TESTS_INTERNAL=On -DFLB_COVERAGE=On \
  -DCMAKE_C_COMPILER=gcc -DCMAKE_CXX_COMPILER=g++ \
  -DFLB_BACKTRACE=Off -DFLB_BINARY=Off -DFLB_SHARED_LIB=Off -DFLB_EXAMPLES=Off

make -C build -j$(nproc)

cd build

ctest

mkdir -p coverage
gcovr -r /src/fluent-bit \
  --filter /src/fluent-bit/src/ --filter /src/fluent-bit/plugins/ \
  --html-details -o coverage/index.html --print-summary

exit ${failed:-0}