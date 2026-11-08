# Retrieval eval: https://github.com/pallets/itsdangerous @ 2.2.0

Embeddings: `local` · 165 chunks · 10 questions

| Configuration | Recall@5 | MRR |
|---|---|---|
| vector only | 1.00 | 0.87 |
| keyword (BM25) only | 1.00 | 0.85 |
| hybrid: vector + keyword | 1.00 | 0.83 |
| hybrid + symbol match (default) | 1.00 | 0.88 |

Rank of the first chunk from the expected file (`-` = not in top 30):

| Question | vector only | keyword (BM25) only | hybrid: vector + keyword | hybrid + symbol match (default) |
|---|---|---|---|---|
| How does the Signer verify a signature? | 1 | 1 | 1 | 1 |
| Where is the timestamp checked against max_age? | 3 | 1 | 2 | 2 |
| How is data base64 encoded and decoded? | 1 | 1 | 1 | 1 |
| What exception is raised when a signed value is too old? | 1 | 1 | 1 | 1 |
| How does the URL safe serializer compress the payload? | 1 | 1 | 1 | 1 |
| How are multiple secret keys supported for key rotation? | 3 | 2 | 3 | 3 |
| When loading, how does the serializer try each signer until one works? | 1 | 1 | 2 | 1 |
| Where is the HMAC digest computed? | 1 | 1 | 1 | 1 |
| How is the signing key derived from the secret key and salt? | 1 | 2 | 1 | 1 |
| Which JSON implementation is used by default and how is it made compact? | 1 | 2 | 1 | 1 |
