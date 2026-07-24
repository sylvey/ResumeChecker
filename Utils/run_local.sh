#!/bin/bash
# Run the Flask scoring service against local MongoDB instead of the shared
# Atlas cluster in .env, so manual/end-to-end testing never writes real data
# into the shared database. Requires `brew services start mongodb-community`.
#
# Usage: ./run_local.sh          (runs server.py)
#        ./run_local.sh agent.py resume.pdf jd.txt   (runs any script the same way)

export MONGO_URI="mongodb://localhost:27017"

if [ "$#" -eq 0 ]; then
    python3 server.py
else
    python3 "$@"
fi