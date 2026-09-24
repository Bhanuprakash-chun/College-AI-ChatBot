"""Generate a small corpus of realistic college PDFs for demos and tests.

These are *sample* policy documents, not real institutional records. Replace
them with your college's actual PDFs by uploading through the admin panel.

    python scripts/generate_sample_documents.py [--out DIR]
"""

import argparse
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from reportlab.lib.enums import TA_JUSTIFY  # noqa: E402
from reportlab.lib.pagesizes import A4  # noqa: E402
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet  # noqa: E402
from reportlab.lib.units import inch  # noqa: E402
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer  # noqa: E402

DOCUMENTS: dict[str, dict] = {
    "attendance_policy.pdf": {
        "title": "Attendance Policy",
        "department": "Academics",
        "document_type": "policy",
        "sections": [
            (
                "Minimum Attendance Requirement",
                "Every student must maintain a minimum of 75% attendance in each subject "
                "during a semester to be eligible to appear for the semester-end examinations. "
                "Attendance is computed on the number of classes actually conducted, counting "
                "lectures, tutorials and laboratory sessions together.",
            ),
            (
                "Condonation of Shortage",
                "Students whose attendance falls between 65% and 75% may apply for condonation "
                "of shortage by submitting a written request with supporting documents, such as "
                "a medical certificate, to the Head of the Department within one week of the end "
                "of the semester. A condonation fee of Rs. 1,000 per subject applies. Condonation "
                "is granted only for genuine reasons such as medical emergencies, bereavement, or "
                "participation in college-approved events.",
            ),
            (
                "Detention",
                "Students whose attendance is below 65% in any subject will be detained and will "
                "not be permitted to appear for the semester-end examination in that subject. "
                "A detained student must re-register for and repeat that subject in a subsequent "
                "semester.",
            ),
            (
                "Laboratory Attendance",
                "Attendance for laboratory sessions is recorded separately from theory attendance "
                "and is mandatory. A student who misses more than three consecutive laboratory "
                "sessions without prior written approval may be awarded zero marks for the "
                "internal laboratory assessment of that subject.",
            ),
            (
                "Monitoring and Grievances",
                "Attendance percentages are published on the student portal every two weeks. "
                "Students must verify their attendance regularly. Any discrepancy should be "
                "reported to the class coordinator within seven days of publication, after which "
                "the recorded attendance is treated as final.",
            ),
        ],
    },
    "examinations_policy.pdf": {
        "title": "Examinations Policy",
        "department": "Examinations",
        "document_type": "policy",
        "sections": [
            (
                "Examination Schedule",
                "Semester-end examinations are conducted twice each academic year, in the last "
                "two weeks of May and the last two weeks of November. The detailed datesheet is "
                "published on the college website and on departmental notice boards at least "
                "three weeks before the examinations begin.",
            ),
            (
                "Passing Criteria",
                "To pass a subject a student must secure a minimum of 40% marks in the "
                "semester-end examination and a minimum of 40% in the aggregate of internal and "
                "external assessment taken together. Subjects carrying a practical component "
                "additionally require a minimum of 50% marks in the practical examination.",
            ),
            (
                "Backlogs and Promotion",
                "A student who fails a subject is recorded as holding a backlog in that subject. "
                "A maximum of four standing backlogs is permitted at any time. A student carrying "
                "more than four backlogs will not be promoted to the next academic year and must "
                "clear the excess backlogs before promotion is considered.",
            ),
            (
                "Revaluation",
                "A student may apply for revaluation of an evaluated answer script within ten "
                "days of the declaration of results, on payment of the prescribed revaluation fee "
                "of Rs. 500 per subject. Revaluation results are normally declared within three "
                "weeks of the last date of application. If the revised marks differ by more than "
                "15%, a third evaluation is carried out and its result is final.",
            ),
            (
                "Supplementary Examinations",
                "Supplementary examinations for backlog subjects are conducted once every "
                "semester, generally in the month immediately following the regular semester-end "
                "examinations. Registration closes fifteen days before the examination begins.",
            ),
            (
                "Malpractice",
                "Any student found using unfair means during an examination will have the "
                "examination of that subject cancelled. Repeat offences may lead to cancellation "
                "of the entire semester's examinations and debarment for up to two semesters, as "
                "decided by the Examination Malpractice Committee.",
            ),
        ],
    },
    "admissions_policy.pdf": {
        "title": "Admissions Policy",
        "department": "Admissions",
        "document_type": "policy",
        "sections": [
            (
                "Eligibility",
                "Admission to the first year of all undergraduate engineering programmes is based "
                "on the candidate's rank in the relevant state or national entrance examination. "
                "The candidate must have passed 10+2 with Physics, Chemistry and Mathematics, "
                "securing a minimum aggregate of 45% marks, relaxed to 40% for candidates "
                "belonging to reserved categories.",
            ),
            (
                "Lateral Entry",
                "Candidates holding a three-year diploma in an appropriate branch of engineering "
                "with a minimum of 45% marks are eligible for lateral entry directly into the "
                "second year, subject to availability of seats and the lateral entry merit list.",
            ),
            (
                "Documents Required at Admission",
                "Candidates must produce the following original documents at the time of "
                "admission: the 10th standard marks memo, the 12th standard or diploma marks "
                "memo, the entrance examination rank card, a transfer certificate from the "
                "institution last attended, a study or bonafide certificate covering the previous "
                "four years, a caste certificate where applicable, an income certificate where "
                "applicable, Aadhaar card, and six recent passport-size photographs. Attested "
                "photocopies of each document must also be submitted.",
            ),
            (
                "Admission Schedule",
                "The admission portal opens in the first week of July each year. The last date "
                "for submission of the completed admission form with fee payment is 31 August. "
                "Late admissions may be considered until 15 September only with the written "
                "approval of the Principal and on payment of a late fee.",
            ),
            (
                "Cancellation and Refund",
                "A request for cancellation of admission must be made in writing. Cancellations "
                "made before the commencement of classes are refunded in full, less a processing "
                "charge of Rs. 1,000. Cancellations made within thirty days of the commencement "
                "of classes are refunded at 50% of the tuition fee. No refund is made thereafter.",
            ),
        ],
    },
    "fees_structure.pdf": {
        "title": "Fee Structure and Payment Rules",
        "department": "Accounts",
        "document_type": "circular",
        "sections": [
            (
                "Tuition Fee",
                "The annual tuition fee for undergraduate engineering programmes is Rs. 85,000 "
                "for candidates admitted under the convener quota and Rs. 1,35,000 for candidates "
                "admitted under the management quota. The fee is revised only with the approval "
                "of the State Fee Regulatory Committee.",
            ),
            (
                "Other Charges",
                "In addition to tuition, students pay a one-time admission charge of Rs. 5,000, "
                "an annual examination fee of Rs. 3,500, a laboratory and library charge of "
                "Rs. 6,000 per year, and an annual student welfare and activities charge of "
                "Rs. 2,500.",
            ),
            (
                "Payment Schedule and Instalments",
                "The full annual fee is payable at the time of admission or re-registration. "
                "Students may apply to pay in two instalments, the first at registration and the "
                "second before 31 December of the same academic year. Instalment facility must be "
                "approved in writing by the Accounts Officer.",
            ),
            (
                "Online Payment",
                "Fees may be paid online through the student portal using net banking, UPI, or a "
                "debit or credit card. A payment receipt is generated immediately and is also "
                "emailed to the student's registered address. Cash payments above Rs. 10,000 are "
                "not accepted at the counter.",
            ),
            (
                "Late Payment Penalty",
                "A late fee of Rs. 100 per day, subject to a maximum of Rs. 3,000, is charged on "
                "fees paid after the due date. Students whose fees remain unpaid for more than "
                "sixty days past the due date will not be issued a hall ticket for the "
                "semester-end examinations.",
            ),
        ],
    },
    "certificates_services.pdf": {
        "title": "Student Certificates and Office Services",
        "department": "Administration",
        "document_type": "handbook",
        "sections": [
            (
                "Bonafide Certificate",
                "A bonafide certificate confirms that the applicant is a currently enrolled "
                "student of the college. To obtain one, the student submits a completed request "
                "form at the Administrative Office counter, stating the purpose, together with a "
                "fee of Rs. 50. The certificate is normally issued within two working days. "
                "Requests may also be raised through the student portal, in which case the "
                "certificate is available for collection within three working days.",
            ),
            (
                "Transfer Certificate",
                "A transfer certificate is issued on completion of the programme or on approved "
                "discontinuation. The student must obtain a no-dues clearance from the library, "
                "the laboratories, the hostel where applicable, and the Accounts section before "
                "the certificate is released. Issue takes five to seven working days after "
                "clearance and costs Rs. 200.",
            ),
            (
                "Migration Certificate",
                "A migration certificate is required when a student moves to another university. "
                "Applications are forwarded to the affiliating university and the certificate is "
                "typically issued within three to four weeks. The prescribed fee is Rs. 500.",
            ),
            (
                "Duplicate Documents and Corrections",
                "A duplicate marks memo may be requested on submission of an affidavit and a copy "
                "of the police complaint where the original was lost, along with a fee of "
                "Rs. 300 per document. Corrections to name or date of birth require supporting "
                "documentary evidence and the written approval of the Principal.",
            ),
            (
                "Office Timings",
                "The Administrative Office is open from 9:30 a.m. to 4:30 p.m. on Monday to "
                "Friday and from 9:30 a.m. to 1:00 p.m. on Saturday. The office is closed on the "
                "second Saturday of each month and on all declared public holidays.",
            ),
        ],
    },
    "courses_curriculum.pdf": {
        "title": "Programme Structure and Curriculum",
        "department": "Academics",
        "document_type": "syllabus",
        "sections": [
            (
                "Programme Duration and Credits",
                "The Bachelor of Technology programme extends over four academic years divided "
                "into eight semesters. A student must earn a total of 160 credits to be awarded "
                "the degree. Lateral entry students join in the third semester and must earn "
                "120 credits.",
            ),
            (
                "Third Year Computer Science Subjects",
                "In the third year, the Computer Science and Engineering curriculum comprises "
                "Design and Analysis of Algorithms, Database Management Systems, Computer "
                "Networks, Operating Systems, Software Engineering, Machine Learning, and Web "
                "Technologies, together with the corresponding laboratory courses in databases, "
                "networks and operating systems.",
            ),
            (
                "Electives",
                "Professional electives begin in the sixth semester. Final-year students choose "
                "two professional electives and one open elective each semester. Elective options "
                "in the final year include Cloud Computing, Natural Language Processing, "
                "Cyber Security, Internet of Things, Computer Vision, and Blockchain Technology. "
                "An elective runs only if at least twenty students register for it.",
            ),
            (
                "Project Work",
                "Every student undertakes a minor project in the seventh semester and a major "
                "project in the eighth semester. The major project carries 12 credits and is "
                "assessed through a mid-term review, a final report, and a viva voce examination "
                "conducted by an external examiner.",
            ),
            (
                "Branch Change",
                "A student may apply to change branch at the end of the first year. Requests are "
                "considered strictly on first-year academic merit, subject to seat availability "
                "in the receiving branch, and require a minimum first-year aggregate of 8.0 CGPA "
                "with no backlogs.",
            ),
        ],
    },
    "placements_handbook.pdf": {
        "title": "Training and Placement Handbook",
        "department": "Placements",
        "document_type": "handbook",
        "sections": [
            (
                "Eligibility for Placement Drives",
                "To participate in campus placement drives a student must have a minimum "
                "aggregate of 6.5 CGPA, no standing backlogs at the time of the drive, and at "
                "least 75% attendance in the current semester. Individual recruiters may set "
                "higher criteria, which are announced with each drive.",
            ),
            (
                "Registration",
                "Students register with the Training and Placement Cell at the beginning of the "
                "seventh semester by completing the placement registration form and uploading an "
                "updated resume to the placement portal. Registration closes on 31 July and "
                "late registrations are not accepted.",
            ),
            (
                "Placement Statistics",
                "In the most recent completed placement season, 412 of 487 eligible students were "
                "placed, giving a placement rate of 84.6%. The average annual package was "
                "Rs. 6.4 lakh, the median was Rs. 5.2 lakh, and the highest package offered was "
                "Rs. 32 lakh.",
            ),
            (
                "Recruiting Organisations",
                "Organisations that recruited on campus during the last season include Tata "
                "Consultancy Services, Infosys, Wipro, Cognizant, Accenture, Capgemini, Tech "
                "Mahindra, Deloitte, Amazon, and a number of product start-ups.",
            ),
            (
                "One Student One Offer",
                "The Cell follows a one-student-one-offer policy. A student who accepts an offer "
                "is withdrawn from further drives, except where a subsequent offer exceeds twice "
                "the value of the accepted package, in which case the student may apply to the "
                "Placement Officer for permission to participate.",
            ),
        ],
    },
    "scholarships_policy.pdf": {
        "title": "Scholarships and Financial Assistance",
        "department": "Scholarships",
        "document_type": "policy",
        "sections": [
            (
                "Government Post-Matric Scholarship",
                "Students belonging to Scheduled Caste, Scheduled Tribe, Backward Class and "
                "Economically Weaker Section categories may apply for the state post-matric "
                "scholarship, which covers tuition fees and provides a maintenance allowance. "
                "The annual family income must not exceed Rs. 2,50,000 for Backward Class and "
                "Economically Weaker Section applicants, and Rs. 2,00,000 for Scheduled Caste and "
                "Scheduled Tribe applicants.",
            ),
            (
                "Merit Scholarship",
                "The college awards a merit scholarship covering 50% of the tuition fee to the "
                "top three students in each branch of each year, determined by the previous "
                "year's aggregate. A full tuition waiver is awarded to any student who places in "
                "the top 1,000 ranks of the state entrance examination.",
            ),
            (
                "Application Process",
                "Applications are submitted through the state scholarship portal between 1 August "
                "and 31 October each year. Students must upload the income certificate, caste "
                "certificate where applicable, the previous year's marks memo, an Aadhaar-linked "
                "bank account passbook, and the college bonafide certificate. The Scholarship "
                "Section verifies applications before forwarding them to the department.",
            ),
            (
                "Disbursement",
                "Verified scholarship amounts are credited directly to the student's "
                "Aadhaar-linked bank account by the state department, normally between January "
                "and March of the academic year. The college does not control the disbursement "
                "date. Students may check the status of their application on the state portal "
                "using their application number.",
            ),
            (
                "Continuation",
                "Continuation of any scholarship in subsequent years requires a minimum of 75% "
                "attendance and promotion to the next year without detention. A student who is "
                "detained forfeits the scholarship for that year.",
            ),
        ],
    },
    "hostel_rules.pdf": {
        "title": "Hostel Rules and Accommodation",
        "department": "Hostel",
        "document_type": "handbook",
        "sections": [
            (
                "Allotment",
                "Hostel accommodation is allotted on application, with priority given to students "
                "whose permanent residence is more than 50 kilometres from the college. "
                "Applications open with the admission process and rooms are allotted on a "
                "first-come, first-served basis within each priority band.",
            ),
            (
                "Hostel Charges",
                "The annual hostel charge is Rs. 72,000 for a two-seater room and Rs. 58,000 for "
                "a four-seater room. These amounts include mess charges, electricity and water, "
                "laundry service, and Wi-Fi. A refundable caution deposit of Rs. 5,000 is "
                "collected at the time of allotment and returned when the student vacates, after "
                "deduction for any damage.",
            ),
            (
                "Mess",
                "The mess serves vegetarian and non-vegetarian meals on a fixed weekly menu "
                "decided by the Mess Committee, on which student representatives sit. Mess "
                "charges are included in the hostel fee and no separate payment is required. "
                "Breakfast is served from 7:30 to 9:00 a.m., lunch from 12:30 to 2:00 p.m., and "
                "dinner from 7:30 to 9:00 p.m.",
            ),
            (
                "Curfew and Leave",
                "Residents must return to the hostel by 9:00 p.m. on weekdays and by 9:30 p.m. on "
                "weekends. Overnight leave requires an online leave request approved by the "
                "warden and countersigned by a parent or guardian. Unauthorised absence at night "
                "is reported to parents and repeated instances may lead to cancellation of "
                "accommodation.",
            ),
            (
                "Conduct",
                "Ragging in any form is strictly prohibited and attracts immediate expulsion from "
                "the hostel in addition to action under the UGC anti-ragging regulations. "
                "Possession of alcohol, tobacco products, narcotics, or any electrical cooking "
                "appliance in the rooms is not permitted.",
            ),
        ],
    },
    "college_general_info.pdf": {
        "title": "General College Information",
        "department": "General",
        "document_type": "handbook",
        "sections": [
            (
                "About the College",
                "The college is an autonomous engineering institution affiliated to the state "
                "technical university and accredited by the National Board of Accreditation. It "
                "offers eight undergraduate programmes and five postgraduate programmes across "
                "engineering and management disciplines.",
            ),
            (
                "Campus Timings",
                "Classes are conducted from 9:00 a.m. to 4:30 p.m. from Monday to Friday and "
                "from 9:00 a.m. to 1:00 p.m. on Saturday. The library remains open from 8:30 "
                "a.m. to 8:00 p.m. on working days and from 9:00 a.m. to 5:00 p.m. on Saturday.",
            ),
            (
                "Library",
                "The central library holds over 60,000 volumes and subscribes to major digital "
                "collections including IEEE Xplore, Springer Link and the DELNET consortium. "
                "An undergraduate student may borrow four books at a time for fourteen days. "
                "An overdue charge of Rs. 2 per day per book applies after the due date.",
            ),
            (
                "Student Support",
                "The student counselling cell provides free and confidential academic and "
                "personal counselling and is open from 10:00 a.m. to 4:00 p.m. on working days. "
                "Each class is assigned a faculty mentor who meets the class once a fortnight. "
                "Grievances may be submitted through the online grievance portal and are "
                "acknowledged within three working days.",
            ),
            (
                "Anti-Ragging and Grievance Redressal",
                "The college maintains a standing Anti-Ragging Committee and an Internal "
                "Complaints Committee. Complaints may be made in person, through the grievance "
                "portal, or to the national anti-ragging helpline. All complaints are treated "
                "confidentially and investigated within seven working days.",
            ),
        ],
    },
}


# Deliberately NOT indexed by seed_demo.py: this one exists so the admin
# "upload -> processing -> ready" flow can be demonstrated live.
DEMO_UPLOAD = {
    "academic_calendar_2025_26.pdf": {
        "title": "Academic Calendar 2025-26",
        "sections": [
            (
                "Odd Semester (I, III, V, VII)",
                "Classes for the odd semester commence on 21 July 2025. The first mid-term "
                "examinations are held from 8 September to 13 September 2025 and the second "
                "mid-term examinations from 3 November to 8 November 2025. The last instruction "
                "day of the odd semester is 14 November 2025.",
            ),
            (
                "Odd Semester End Examinations",
                "Odd semester end examinations are scheduled from 17 November 2025 to "
                "29 November 2025. Practical examinations are conducted from 1 December to "
                "6 December 2025. The winter vacation runs from 8 December 2025 to "
                "28 December 2025.",
            ),
            (
                "Even Semester (II, IV, VI, VIII)",
                "Classes for the even semester commence on 29 December 2025. The first mid-term "
                "examinations are held from 16 February to 21 February 2026 and the second "
                "mid-term examinations from 13 April to 18 April 2026. The last instruction day "
                "of the even semester is 2 May 2026.",
            ),
            (
                "Even Semester End Examinations",
                "Even semester end examinations are scheduled from 18 May 2026 to 30 May 2026, "
                "followed by practical examinations from 1 June to 6 June 2026. The summer "
                "vacation begins on 8 June 2026. Supplementary examinations for both semesters "
                "are held from 22 June to 30 June 2026.",
            ),
            (
                "Holidays and Events",
                "The college remains closed on all gazetted public holidays. The annual technical "
                "festival is held on 20 and 21 February 2026 and the annual sports meet from "
                "5 March to 7 March 2026. Instruction is suspended on these days, and attendance "
                "is granted to registered participants.",
            ),
        ],
    }
}


def build_pdf(path: Path, title: str, sections: list[tuple[str, str]]) -> None:
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "DocTitle",
        parent=styles["Title"],
        fontSize=18,
        spaceAfter=18,
    )
    heading_style = ParagraphStyle(
        "SectionHeading",
        parent=styles["Heading2"],
        fontSize=12.5,
        spaceBefore=12,
        spaceAfter=6,
    )
    body_style = ParagraphStyle(
        "Body",
        parent=styles["BodyText"],
        fontSize=10.5,
        leading=15,
        alignment=TA_JUSTIFY,
    )

    doc = SimpleDocTemplate(
        str(path),
        pagesize=A4,
        title=title,
        author="College Administration",
        leftMargin=0.9 * inch,
        rightMargin=0.9 * inch,
        topMargin=0.9 * inch,
        bottomMargin=0.9 * inch,
    )

    story = [Paragraph(title, title_style), Spacer(1, 6)]
    for heading, body in sections:
        story.append(Paragraph(heading, heading_style))
        story.append(Paragraph(body, body_style))
    doc.build(story)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out",
        default=str(BACKEND_DIR.parent / "documents" / "samples"),
        help="Directory to write the sample PDFs into.",
    )
    args = parser.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    for filename, spec in DOCUMENTS.items():
        target = out_dir / filename
        build_pdf(target, spec["title"], spec["sections"])
        print(f"  wrote {target.name:<32} ({target.stat().st_size / 1024:.1f} KB)")

    print(f"\n{len(DOCUMENTS)} sample PDFs written to {out_dir}")

    demo_dir = out_dir.parent / "demo-upload"
    demo_dir.mkdir(parents=True, exist_ok=True)
    for filename, spec in DEMO_UPLOAD.items():
        target = demo_dir / filename
        build_pdf(target, spec["title"], spec["sections"])
        print(f"  wrote {target.name:<32} ({target.stat().st_size / 1024:.1f} KB)  <- live upload demo")

    print("\nIndex the samples with: python scripts/seed_demo.py")
    print(f"Upload the file in {demo_dir} through the admin panel to demo live ingestion.")


if __name__ == "__main__":
    main()
