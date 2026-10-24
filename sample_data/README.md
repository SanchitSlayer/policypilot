# Sample data

Put 3–5 public policy PDFs here before Phase 1 (they are gitignored). Good choices:

- RBI Master Direction – Know Your Customer (KYC) Direction, 2016 (as updated)
- RBI Guidelines on Digital Lending
- A sample company privacy policy

Two fictional demo documents are committed (regenerate with `python -m app.scripts.make_sample_data` from `backend/`):

- `sample_internal_kyc_data_policy.pdf`: upload as **policy**. Nine numbered rules (address proof, Aadhaar masking, five-year retention, consent, six-hour breach reporting…).
- `sample_vendor_kyc_agreement.pdf`: upload as **contract**. Eleven clauses; clauses 3, 4, 5, 6 and 8 deliberately break the policy (self-declared address, full Aadhaar storage, 12-month retention, sharing without consent, 72-hour breach notice).
