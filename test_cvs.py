import asyncio
import os
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from app.services.ai.evaluator import evaluate_cv

cvs = {
    "Tran Ngoc Thuc": """Tran Ngoc Thuc
HCMC, Vietnam (+84) 869 306 922 ngocthuc230902@gmail.com LinkedIn
SUMMARY
Impact-driven and solution-oriented individual with strong ambition for growth. In search of experience
where I can express my interests in Human Resources Management along with applying my Problem
Solving & Project Management skill to deliver value to customers and drive impacts for the organization.
EXPERIENCE
ABeam Consulting Vietnam Apr 2024 – Present
Integrated Enterprise Solution Intern HCMC, Vietnam
● Designed integrated SAP solutions and customized HXM modules to align with clients' objectives and business requirements
● Conducted business process analysis to identify areas for improvement and recommended solutions to streamline operations
Schneider Electric Vietnam Apr 2023 – Sep 2023
HRBP cum HRS Intern HCMC, Vietnam
● Modified and consolidated organization chart monthly within 19 departments/business units
● Assisted in planning, implementing Employees Engagement
● Provided service on internal & external inquiries regarding employee activities and Talent Development
● Promoted and ensured corporate compulsory learning course: Schneider Essentials, Digital Boost, resulted in 90% completion rate
AIESEC in Vietnam Feb 2023 – Aug 2023
National Membership Experience Product Development - Talent Management HCMC, Vietnam
● Was responsible for membership product development (MXP) to drive members performance in terms of product launching
AIESEC in HCME Jul 2022 – Jan 2023
Finance and Legality Team Leader - Finance HCMC, Vietnam
● Led a team of 2 members to ensure finance standards implementation, grow local entity finance up to 25M, with profit margin of 38%
EDUCATION
Bachelor Degree in International Economic Relations | GPA: 3.4/4.0 Sep 2020 – 2024
University of Economics and Law, Vietnam National University, HCM
AWARDS
Top 8 Human Resources of Ung Vien Tai Nang 2023 by HRC - FTU Hanoi Dec 2023
Champion of 21st AmCham Scholarship by The American Chamber of Commerce Jun 2023
SKILLS
Language: Limited Proficiency Working in English
Certificates: Project Management Professional by Atoha Institute, SAP by BI-Lab
Technical Skills: MS Office, Adobe Photoshop, Power BI""",

    "Tran Ngoc Anh Thu": """Tran Ngoc Anh Thu
Finance Intern
Thu Duc City, Ho Chi Minh City | 0902 693 671 | trngocanhthu803@gmail.com
A dedicated and ambitious junior majoring in International Finance and seeking a challenging as well as rewarding position in the field of Finance, where I can leverage my analytical skills, forecasting, and passion for financial analysis, strategic planning, and risk management skills.
Experience
Royal HaskoningDHV Vietnam Dec 2023 - Apr 2024
Financial Accounting Intern
Aided senior accountants in crafting precise financial reports, emphasizing AP, AR, prepayment, and tax.
Supported tax preparation through organization, calculations, and ensuring compliance for timely submissions.
Supported building financial modeling, facilitating effective budget tracking, forecasting and resolved account discrepancies.
KPMG Vietnam Jul 2023 - Sep 2023
Summer Intern - Financial Auditing
Led detailed credit reviews and ensured tax table accuracy in IVB Bank's audit team;
Investigated the legal framework for investment funds and meticulously verified financial data to ensuring compliance.
Education
Foreign Trade University - Ho Chi Minh City Campus 2021-2025
Major: International finance, GPA: 8.01/10 (3.31/4.0)
Achievement
E!CONTRAIN 2024 competion 2024
Collaborated with two peers to solve a case study for a business aiming to enter a new market within 72 hours
Foreign Trade University Scientific Research Competition 2023
Led a 5-member team, devising plans for timely completion of research tasks. Awarded Third Prize.
Certificate: IELTS: 7.0, CFA Level I (Nov, 2023)""",

    "TRAN MAI LINH": """TRAN MAI LINH
Ho Chi Minh, Vietnam | +84 847 106 679 | linhtranmai0825@gmail.com | LinkedIn
CAREER ORIENTATION
As a third-year Finance major, I am passionate about analysis and working with numbers. With a proactive attitude, a thirst for learning, and ambitious goals, I aspire to pursue opportunities for personal and professional growth in roles such as FP&A position.
EDUCATION
Foreign Trade University HCMC, Vietnam
Bachelor of Banking and International Finance Class of 2025
Cummulative GPA: 3.3/4.0
WORKING EXPERIENCES
Sun Life Vietnam, Sun Life is a leading financial services organization. HCMC, Vietnam
Saturn Intern – Procurement Rotation Jun 2023 – Sep 2023
Conducted research to identify suitable vendors for the company's tour and customer gift segments;
Obtained price quotes and compared vendors to select the optimal supplier;
EXTRACURRICULAR ACTIVITIES
ACTION Club, FTU2's outstanding 20-year student organization HCMC, Vietnam
Project Leader – Business Solutions Oct 2022 – Nov 2023
Led a team of 5 members in devising project development strategies spanning four key dimensions: partnership, product, human resources, and marketing.
Conducted extensive research to ascertain client needs, customized employee branding (EB) activity packages
External Relations Specialist - Doanh Nhan Tap Su Competition 2022 Nov 2021 – Jun 2022
Conducted needs assessments, developed proposals, and approached over 40 accompanying sponsors for the contest.
AWARDS
Champion of Investment Analysis Expert 2024
1st Prize of Olympic Econometrics And Applications 2023
SKILLS
Language: English, Vietnamese.
Technical Skills: Microsoft Office, Research, Financial Statement Analysis""",

    "TRAN MAI CHI": """TRAN MAI CHI (INTERN)
Ho Chi Minh City | tranmaichi2510@gmail.com | (+84) 919 150 377
With a data-driven mindset and result-oriented ability, I am eager to improve skills, learn new knowledge and embrace challenges, especially in the field of Sales via an entry-level position in a professional environment.
EDUCATION
FOREIGN TRADE UNIVERSITY, HO CHI MINH CITY 2021 – 2025 (Expected)
Major: Bachelor’s Degree in International Business Administration, GPA: 3.49/4.0
WORK EXPERIENCE
D.LYN’K CLINIC 04/2023 – 07/2023
DIGITAL SALES INTERN (E-COMMERCE)
Ensured visibility of the brand portfolio by designing and content creation within the e-commerce marketplaces (Shopee, Tiki, Lazada, BeautyX);
Managed order tracking and stock availability daily in order to mitigate the risk of out of stock;
ACHIEVEMENTS
TOP 1 SALES – ACDEMY 2023 01/2024
Selected among the top after a multi-stage selection process (CV, training programs, individual interview) demonstrating strong skills.
CHAMPION – Career Fronstart 2023 – Case sponsored by NinjaVan (Business Development) 09/2023
Conducted a Market research for Baked industry and built Marketing Plan for launching a new product for a company in 2 years.
TOP 3 – E!Contest X 2023 – Case sponsored by ZaloPay (Fintech Industry) 06/2023
Surpass 400+ candidates to be one of the 6 best teams competing in the Final Night;
EXTRACURRICULAR ACTIVITIES
Research Club for Students - FTU HCMC 12/2021 – 10/2023
VICE PRESIDENT 07/2022 – 10/2023
Led and implemented strategic directions to four departments of 50+ members including L&D, HR, External Relations and Marketing, improved retention rates by 12%;
Managed 15+ significant projects that are finished on budget, and on schedule;
DAZONE 2022, a largest Data Analytics Competition 01/2022 – 07/2022
LEADER OF EXTERNAL RELATIONS AND FINANCIAL DEPARTMENT
Collaborated with 30+ sponsors and developed strong relationships with key partners like VNG, ZaloPay, Buzzmetrics and etc;
Gained 20 big deals with the total honorary of 65.000.000 VND in cash, exceeded +201% KPI;
CERTIFICATES
Data Analysis – PowerBI (Tomorrow Marketers)
SKILL SETS
Technical skills: Data Analysis (SQL – Basic, PowerBI – Basic) | Microsoft Office
Soft skills: Teamwork | Communication | Problem-solving;
Languages: English (IELTS 7.0 – Level C1)/ Vietnamese (Native)"""
}

async def run_tests():
    for name, text in cvs.items():
        print(f"\\n{'='*40}")
        print(f"Testing CV: {name}")
        print(f"{'='*40}")
        for i in range(1, 6):
            try:
                result = await evaluate_cv(text)
                print(f"Test {i}: Score = {result.score:.1f}")
            except Exception as e:
                print(f"Test {i}: Error = {e}")

if __name__ == "__main__":
    asyncio.run(run_tests())
