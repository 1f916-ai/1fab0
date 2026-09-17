#!/bin/sh
# Fetch the MaleCNS v1.0 flat-connectome tables (CC BY 4.0) and verify the canonical weights hash.
# Source: https://male-cns.janelia.org/download/
set -e
B=https://storage.googleapis.com/flyem-male-cns/v1.0/connectome-data/flat-connectome
D=${1:-data/malecns}; mkdir -p "$D"
for f in body-annotations-male-cns-v1.0-minconf-0.5.feather body-neurotransmitters-male-cns-v1.0.feather connectome-weights-male-cns-v1.0-minconf-0.5.feather; do
  [ -f "$D/$f" ] || curl -sS -L -o "$D/$f.part" "$B/$f" && { [ -f "$D/$f" ] || mv "$D/$f.part" "$D/$f"; }
done
echo "e35da783d1c686b2b58b3b87cd6a403ae43bfcfba8bff28e08ef752c1a56afc1  $D/connectome-weights-male-cns-v1.0-minconf-0.5.feather" | shasum -a 256 -c -
