#!/bin/bash

# Run all three servers in the same terminal, each in the background

python3 ../basic_server/src/notes_server.py &
python3 ../basic_server/src/greeting_server.py &
python3 ../basic_server/src/twitter_server.py &

# Wait for all background jobs to finish
wait
