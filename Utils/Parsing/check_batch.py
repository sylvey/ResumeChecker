from dotenv import load_dotenv
load_dotenv()
import anthropic
c = anthropic.Anthropic()
bid = open('scores.jsonl.batch_ids.txt').read().strip()
b = c.messages.batches.retrieve(bid)
print('batch id:', bid)
print('status:', b.processing_status)
print('counts:', b.request_counts)
