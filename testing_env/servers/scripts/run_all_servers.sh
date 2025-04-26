#!/bin/bash

# Run all three servers in the same terminal, each in the background

python3 ../src/basic_server/notes_server.py &
python3 ../src/basic_server/greeting_server.py &
python3 ../src/basic_server/twitter_server.py &

# Wait for all background jobs to finish
wait
