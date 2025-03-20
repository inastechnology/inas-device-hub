#! /bin/bash

# check arguments
if [ "$#" -ne 1 ]; then
    echo "Usage: $0 <frontend|backend>"
    exit 1
fi

type=$1

# load rye env
source "$HOME/.rye/env"

# start by rye
if [ "$type" == "backend" ]; then
    rye run backend
elif [ "$type" == "frontend" ]; then
    rye run frontend
else
    echo "Usage: $0 <frontend|backend>"
    exit 1
fi
