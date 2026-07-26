# Update Environment

`pip install -r requirements.txt`

# Run

`python server.py`

# Local testing (without touching the shared Atlas database)

`.env`'s `MONGO_URI` points at the shared Atlas cluster, so running `server.py`
or `agent.py` directly writes real documents there. For manual/end-to-end
testing, run them through `run_local.sh` instead, which points MONGO_URI at
your local MongoDB (`brew services start mongodb-community` first):

```
./run_local.sh              # runs server.py against local MongoDB
./run_local.sh agent.py resume.pdf jd.txt   # any script, same way
```

`pytest` (`test_tools.py`) already defaults to local MongoDB on its own --
it never loads `.env` -- so no wrapper is needed there.
