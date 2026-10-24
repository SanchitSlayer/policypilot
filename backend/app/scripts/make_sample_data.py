"""Write the fictional demo corpus: three policies and a vendor contract that breaks them.

    python -m app.scripts.make_sample_data            # writes to ../sample_data
    python -m app.scripts.make_sample_data out_dir/

Every document is fictional ("Northwind Bank"). Policies are laid out one list entry per PDF
page, so the evaluation test set (eval/testset.json) can name exact expected pages. The
contract has deliberate problems (clauses 3, 4, 5, 6 and 8) for the Contract Review demo.
"""

import argparse
from pathlib import Path

from app.utils.simple_pdf import make_pdf, make_text_pdf

DEFAULT_DIR = Path(__file__).resolve().parents[3] / "sample_data"

POLICY_FILENAME = "sample_internal_kyc_data_policy.pdf"
LENDING_FILENAME = "sample_digital_lending_policy.pdf"
SECURITY_FILENAME = "sample_information_security_standard.pdf"
CONTRACT_FILENAME = "sample_vendor_kyc_agreement.pdf"

KYC_POLICY_PAGES = [
    # page 1
    """NORTHWIND BANK LIMITED
INTERNAL KYC AND CUSTOMER DATA POLICY (FICTIONAL SAMPLE, VERSION 3.2)

1. Purpose and scope. This policy sets the minimum Know Your Customer (KYC), anti-money \
laundering and customer data requirements for Northwind Bank and for every vendor that \
processes customer data on its behalf. Vendor contracts must not permit practices weaker \
than this policy.

2. Definitions. An officially valid document (OVD) is a passport, driving licence, voter \
identity card, job card issued by NREGA, or proof of possession of an Aadhaar number. A \
beneficial owner of a company is any natural person who owns more than 10 percent of its \
shares or capital. A politically exposed person (PEP) is an individual entrusted with a \
prominent public function, such as a head of state, senior politician or senior judicial \
official.

3. Roles. The Principal Officer, a member of senior management, is responsible for \
monitoring transactions and reporting to the Financial Intelligence Unit (FIU-IND). The \
Designated Director, appointed by the Board, is responsible for overall compliance with \
this policy.""",
    # page 2
    """4. Customer acceptance. No account may be opened in an anonymous or fictitious name. No \
account may be opened where customer due diligence cannot be completed because the customer \
does not cooperate or does not provide the required documents.

5. Customer identification and proof of address. Address must be verified using an \
officially valid document. A customer's self-declaration of address is not acceptable as \
proof of address under any circumstances. A utility bill not older than two months may be \
accepted as a deemed OVD for a limited period, and the customer must then submit an OVD with \
the current address within three months.

6. Video-based customer identification (V-CIP). Customers may be identified through a live \
video call conducted by a trained Bank official. The customer's live location must be \
geo-tagged and must be within India. The video recording and the audit trail must be \
stored securely and retained like other KYC records.""",
    # page 3
    """7. Handling of Aadhaar numbers. Neither the Bank nor any vendor may store a customer's full \
Aadhaar number. The first eight digits must be redacted or masked before any copy of an \
Aadhaar document is stored. Offline Aadhaar XML files used for verification must not be more \
than three days old.

8. Risk categorisation. Every customer is classified as low, medium or high risk. Politically \
exposed persons, non-resident customers and customers with complex ownership structures are \
classified as high risk. Risk categories are reviewed at least once every six months.

9. Enhanced due diligence. Accounts of politically exposed persons require approval from \
senior management before they are opened. For all high-risk customers the Bank must \
establish the source of funds and source of wealth, and monitor transactions more closely.""",
    # page 4
    """10. Periodic updation of KYC. KYC must be updated at least once every two years for \
high-risk customers, once every eight years for medium-risk customers and once every ten \
years for low-risk customers. Customers must receive at least three reminders before the \
due date. If KYC is not updated within 30 days of the due date, the account may be partially \
frozen.

11. Record retention. KYC records and identification documents must be preserved for at \
least five years after the business relationship with the customer has ended or the account \
has been closed, whichever is later. Records of transactions must be preserved for at least \
five years from the date of the transaction. Records must not be destroyed earlier and must \
be made available to competent authorities on request.""",
    # page 5
    """12. Regulatory reporting. Cash transaction reports for cash transactions above Rs. 10 lakh \
must be filed with FIU-IND every month, by the 15th day of the following month. A suspicious \
transaction report must be filed within seven working days of concluding that a transaction \
is suspicious.

13. Consent and data sharing. Customer data may be shared with a third party only with the \
customer's explicit, informed consent and only for the purpose stated at the time of \
consent. Customer data must never be used for marketing or shared with marketing partners \
without a separate opt-in consent.

14. Vendors and outsourcing. Vendors must give the Bank and the Reserve Bank of India \
unrestricted access to premises, systems and records for audit and inspection. Vendors must \
not sub-contract any processing of customer data without the Bank's prior written approval. \
Vendors must report any security incident or data breach affecting customer data to the \
Bank within six hours of detection. All customer data, including backups, must be stored \
only on systems located in India.

15. Training and review. All staff complete AML and KYC training every year. The Board \
reviews this policy at least once a year.""",
]

LENDING_POLICY_PAGES = [
    # page 1
    """NORTHWIND BANK LIMITED
DIGITAL LENDING POLICY (FICTIONAL SAMPLE, VERSION 1.4)

1. Scope. This policy applies to all loans sourced or serviced through digital lending apps \
(DLAs), whether operated by the Bank or by a lending service provider (LSP) engaged by it.

2. Disbursal and repayment. Loan amounts must be disbursed directly into the bank account of \
the borrower. Disbursal through a pass-through account or pool account of any LSP or third \
party is prohibited. Repayments must be made directly into the Bank's account, without \
passing through any account of an LSP.""",
    # page 2
    """3. Key Fact Statement. Before the loan agreement is executed, the borrower must receive a \
Key Fact Statement (KFS) in a standard format. The KFS must state the annual percentage rate \
(APR), which is the all-inclusive cost of the loan, the recovery mechanism, the details of \
the grievance redressal officer, and the cooling-off period.

4. Cooling-off period. Borrowers may exit a digital loan during a cooling-off period by \
repaying the principal and the proportionate APR, without any penalty. The cooling-off \
period is at least three days for loans with a tenor of seven days or more, and at least one \
day for loans with a tenor of less than seven days.""",
    # page 3
    """5. Fees and charges. No fee or charge that is not mentioned in the KFS may be charged to \
the borrower. Fees payable to an LSP are paid by the Bank and must not be charged to the \
borrower directly.

6. Borrower data. Digital lending apps may collect only the data needed for the loan, with \
the borrower's explicit consent. Apps must not access the borrower's contacts, media files \
or call logs. One-time access to the camera, microphone and location is allowed only for \
onboarding. Borrowers may withdraw consent and ask for their data to be deleted.

7. Credit limits. A borrower's credit limit must not be increased automatically. Any increase \
requires the borrower's explicit consent, which must be recorded.""",
    # page 4
    """8. Grievance redressal. Every DLA and LSP must have a nodal grievance redressal officer \
whose contact details are shown in the app and on the website. Complaints must be resolved \
within 30 days. If a complaint is not resolved within 30 days, the borrower may escalate it \
to the RBI Ombudsman under the Integrated Ombudsman Scheme.

9. Recovery practices. Recovery agents must not harass or intimidate borrowers. The name and \
contact details of the recovery agent must be shared with the borrower before the agent \
contacts them. Recovery calls may be made only between 8 a.m. and 7 p.m.

10. Credit reporting. Every loan disbursed through a DLA must be reported to the credit \
information companies, regardless of its tenor.""",
]

SECURITY_STANDARD_PAGES = [
    # page 1
    """NORTHWIND BANK LIMITED
INFORMATION SECURITY STANDARD (FICTIONAL SAMPLE, VERSION 2.0)

1. Scope. This standard applies to all Bank systems and to every vendor system that stores \
or processes Bank data.

2. Access control. Multi-factor authentication is mandatory for all remote access and for \
all privileged accounts. Privileged access rights are reviewed every quarter. Access for \
employees who leave the Bank must be revoked within 24 hours of their exit. Passwords must \
be at least 14 characters long; periodic forced password changes are not required, but \
passwords must be changed immediately if a compromise is suspected.""",
    # page 2
    """3. Encryption. Data at rest must be encrypted with AES-256. Data in transit must use TLS \
1.2 or higher. Encryption keys must be stored in a hardware security module or a managed key \
service and rotated at least once a year.

4. Logging and monitoring. Security logs from all critical systems must be retained for at \
least 180 days and must be monitored by the security operations centre around the clock.

5. Backups and recovery. Critical systems are backed up every day, and restores are tested \
every quarter. For critical systems the recovery point objective (RPO) is four hours and the \
recovery time objective (RTO) is eight hours.""",
    # page 3
    """6. Incident response. Security incidents are classified by severity. Cyber security \
incidents must be reported to CERT-In and to the Reserve Bank of India within six hours of \
being noticed. Customers whose personal data is affected by a breach must be informed within \
72 hours.

7. Vendor security. Critical vendors must undergo a security assessment every year and must \
hold a current ISO 27001 certificate or a SOC 2 Type II report.

8. Exceptions. Exceptions to this standard must be approved by the Chief Information Security \
Officer (CISO) and are valid for at most 90 days.""",
]

# Joined text of the KYC policy (used by tests that only need the content).
POLICY = "\n\n".join(KYC_POLICY_PAGES)

CONTRACT = """KYC VERIFICATION SERVICES AGREEMENT (FICTIONAL SAMPLE)
Between Northwind Bank Limited ("Bank") and DataVerify Solutions Private Limited ("Vendor")

1. Parties and effective date. This Agreement is made on 1 April 2026 between the Bank and the \
Vendor, each a "Party". It takes effect on signature by both Parties.

2. Definitions. "Customer Data" means all personal data of the Bank's customers received or \
generated by the Vendor under this Agreement. "Services" means the services described in \
clause 3.

3. Scope of services. The Vendor shall perform customer identity and address verification for \
new accounts. Where a customer cannot readily produce documents, the Vendor may accept the \
customer's self-declaration of address in place of documentary proof to avoid onboarding delays.

4. Aadhaar data. To allow quick re-verification, the Vendor shall store the complete Aadhaar \
number of each customer, together with a copy of the Aadhaar card, in its verification database.

5. Data retention and deletion. The Vendor shall retain Customer Data and KYC records for twelve \
(12) months after termination of this Agreement and shall then permanently delete them.

6. Use and sharing of data. The Vendor may share Customer Data with its affiliates and marketing \
partners to improve and promote its services, without further notice to customers.

7. Audit and inspection. The Vendor shall give the Bank and the Reserve Bank of India access to \
its premises, systems and records for audit and inspection at any time on reasonable notice.

8. Security incidents. The Vendor shall notify the Bank of any data breach affecting Customer \
Data within seventy-two (72) hours of becoming aware of it.

9. Data location. All Customer Data, including backups, shall be stored on servers located in \
India.

10. Sub-contracting. The Vendor shall not engage any sub-contractor to process Customer Data \
without the prior written approval of the Bank.

11. Governing law. This Agreement is governed by the laws of India, and the courts at Mumbai \
have exclusive jurisdiction.
"""

POLICIES: dict[str, list[str]] = {
    POLICY_FILENAME: KYC_POLICY_PAGES,
    LENDING_FILENAME: LENDING_POLICY_PAGES,
    SECURITY_FILENAME: SECURITY_STANDARD_PAGES,
}


def write_samples(out_dir: Path) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for filename, pages in POLICIES.items():
        path = out_dir / filename
        path.write_bytes(make_pdf(pages))
        written.append(path)
    contract = out_dir / CONTRACT_FILENAME
    contract.write_bytes(make_text_pdf(CONTRACT))
    written.append(contract)
    return written


def main() -> None:
    parser = argparse.ArgumentParser(description="Write the fictional demo policies and contract.")
    parser.add_argument("out_dir", nargs="?", type=Path, default=DEFAULT_DIR)
    args = parser.parse_args()
    for path in write_samples(args.out_dir):
        print(f"wrote {path}")


if __name__ == "__main__":
    main()
