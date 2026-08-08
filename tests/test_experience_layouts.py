import datetime as dt
import unittest

from kriterion.experience import (
    _entry_role_identity,
    build_date_based_entries_from_lines,
    compute_devops_roles,
    has_experience_layout_anomaly,
    is_date_range_line,
    is_education_program,
    is_experience_entry,
)


class ExperienceLayoutTests(unittest.TestCase):
    def lines(self, text: str) -> list[tuple[int, str]]:
        return [(1, line) for line in text.splitlines()]

    def test_standalone_dates_above_titles_do_not_steal_previous_content(self) -> None:
        source = self.lines(
            "June 2025 - Present\n"
            "Cloud Architect & Team Lead | PwC\n"
            "\uf0b7\n"
            "Built GCP and Kubernetes platforms.\n"
            "July 2023 - June 2025\n"
            "Solutions Architect - Cloud and DevOps | Siemens\n"
            "\uf0b7\n"
            "Managed AWS security infrastructure.\n"
            "June 2021 - June 2023\n"
            "Tech Lead - DevOps and Cloud (Lead Engineer) | ITWORX\n"
            "\uf0b7\n"
            "Designed AWS platforms.\n"
            "December 2019 - April 2021\n"
            "Sr. DevOps Engineer | Dell Technologies\n"
            "\uf0b7\n"
            "Managed Kubernetes clusters.\n"
            "July 2019 - December 2019\n"
            "Sr. DevOps and Release Engineer | ITWORX\n"
            "\uf0b7\n"
            "Implemented AWS delivery pipelines.\n"
            "March 2017 - July 2019\n"
            "DevOps Engineer | ITWORX\n"
            "\uf0b7\n"
            "Automated AWS infrastructure."
        )

        entries = build_date_based_entries_from_lines(source)
        self.assertEqual(len(entries), 6)
        self.assertEqual(
            [entry.lines[:2] for entry in entries],
            [
                source[0:2],
                source[4:6],
                source[8:10],
                source[12:14],
                source[16:18],
                source[20:22],
            ],
        )
        self.assertEqual(entries[0].lines[-1][1], "Built GCP and Kubernetes platforms.")
        self.assertNotIn("Built GCP and Kubernetes platforms.", entries[1].text())

        roles, _, ambiguity = compute_devops_roles(entries)
        self.assertFalse(ambiguity)
        self.assertEqual(
            [role.title for role in roles],
            [
                "DevOps Engineer",
                "Sr. DevOps and Release Engineer",
                "Sr. DevOps Engineer",
                "Tech Lead - DevOps and Cloud (Lead Engineer)",
                "Solutions Architect - Cloud and DevOps",
                "Cloud Architect & Team Lead",
            ],
        )
        self.assertEqual(
            [role.company for role in roles],
            ["ITWORX", "ITWORX", "Dell Technologies", "ITWORX", "Siemens", "PwC"],
        )

    def test_title_before_date_remains_supported(self) -> None:
        entries = build_date_based_entries_from_lines(
            self.lines(
                "DevOps Engineer | Acme\n"
                "January 2020 - December 2022\n"
                "• Managed AWS infrastructure."
            )
        )

        roles, _, _ = compute_devops_roles(entries)
        self.assertEqual(roles[0].title, "DevOps Engineer")
        self.assertEqual(roles[0].company, "Acme")

    def test_title_and_date_on_same_line_remains_supported(self) -> None:
        entries = build_date_based_entries_from_lines(
            self.lines(
                "DevOps Engineer | Acme | January 2020 - December 2022\n"
                "• Managed AWS infrastructure."
            )
        )

        roles, _, _ = compute_devops_roles(entries)
        self.assertEqual(roles[0].title, "DevOps Engineer")
        self.assertEqual(roles[0].company, "Acme")

    def test_title_company_date_layout_keeps_roles_and_dates_aligned(self) -> None:
        entries = build_date_based_entries_from_lines(
            self.lines(
                "Senior Linux Technical Consultant\n"
                "All for One Group SE, Heidelberg, Germany\n"
                "Aug 2024 - Present\n"
                "• Maintained infrastructure with Puppet and Ansible.\n"
                "Senior Cloud Application & Infrastructure Engineer\n"
                "Global Brands Group, Remote\n"
                "Jul 2023 - Aug 2024\n"
                "• Automated AWS landing-zone deployments.\n"
                "Cloud Architect\n"
                "DigitalPath.ae, UAE\n"
                "Aug 2022 - May 2023\n"
                "• Designed scalable cloud architectures.\n"
                "Senior Telco Cloud Implementation & Operations Engineer\n"
                "Benya Systems, Egypt\n"
                "Sep 2021 - Jul 2022\n"
                "• Operated OpenStack infrastructure with Prometheus and Grafana.\n"
                "IT Data Center Operation & DevOps Engineer\n"
                "Telecom Egypt\n"
                "Jun 2019 - 2021 Jun\n"
                "• Automated system operations with Ansible and Kubernetes.\n"
                "Field Operation Engineer\n"
                "TE Data, Egypt\n"
                "Mar 2018 - 2019 May\n"
                "• Delivered operational support for field technicians.\n"
                "Network Engineer\n"
                "General Electric, Egypt\n"
                "Mar 2017 - 2018 May\n"
                "• Handled network installations and repairs.\n"
                "Network Engineer\n"
                "Comm Net Group, Egypt\n"
                "Mar 2017 - 2018 May\n"
                "• Set up employee workstations."
            )
        )

        self.assertEqual(
            [entry.head(3) for entry in entries],
            [
                "Senior Linux Technical Consultant | All for One Group SE, Heidelberg, Germany | Aug 2024 - Present",
                "Senior Cloud Application & Infrastructure Engineer | Global Brands Group, Remote | Jul 2023 - Aug 2024",
                "Cloud Architect | DigitalPath.ae, UAE | Aug 2022 - May 2023",
                "Senior Telco Cloud Implementation & Operations Engineer | Benya Systems, Egypt | Sep 2021 - Jul 2022",
                "IT Data Center Operation & DevOps Engineer | Telecom Egypt | Jun 2019 - 2021 Jun",
                "Field Operation Engineer | TE Data, Egypt | Mar 2018 - 2019 May",
                "Network Engineer | General Electric, Egypt | Mar 2017 - 2018 May",
                "Network Engineer | Comm Net Group, Egypt | Mar 2017 - 2018 May",
            ],
        )

        roles, total_months, ambiguity = compute_devops_roles(entries)

        self.assertFalse(ambiguity)
        self.assertEqual(
            [role.title for role in roles],
            [
                "IT Data Center Operation & DevOps Engineer",
                "Senior Telco Cloud Implementation & Operations Engineer",
                "Cloud Architect",
                "Senior Cloud Application & Infrastructure Engineer",
                "Senior Linux Technical Consultant",
            ],
        )
        self.assertEqual(
            [role.company for role in roles],
            [
                "Telecom Egypt",
                "Benya Systems, Egypt",
                "DigitalPath.ae, UAE",
                "Global Brands Group, Remote",
                "All for One Group SE, Heidelberg, Germany",
            ],
        )
        self.assertEqual(
            [(role.start, role.end) for role in roles],
            [
                (dt.date(2019, 6, 1), dt.date(2021, 6, 1)),
                (dt.date(2021, 9, 1), dt.date(2022, 7, 1)),
                (dt.date(2022, 8, 1), dt.date(2023, 5, 1)),
                (dt.date(2023, 7, 1), dt.date(2024, 8, 1)),
                (dt.date(2024, 8, 1), dt.date.today()),
            ],
        )
        self.assertNotIn("Field Operation Engineer", [role.title for role in roles])
        self.assertNotIn("Network Engineer", [role.title for role in roles])
        self.assertEqual(total_months, 84)

    def test_title_company_date_supports_it_administration_at_university(self) -> None:
        entries = build_date_based_entries_from_lines(
            self.lines(
                "DevOps Engineer\n"
                "Cloud4Rain\n"
                "12/2024 – present\n"
                "• Deployed Kubernetes clusters on AWS.\n"
                "IT Administration\n"
                "Faculty of Artificial Intelligence, Badr University, Assiut\n"
                "01/2024 – 12/2024\n"
                "• Administered Linux servers and automated patching.\n"
                "Teaching assistant\n"
                "Faculty of Artificial Intelligence, Badr University, Assiut\n"
                "01/2024 – 12/2024\n"
                "• Led programming and networking lab sessions.\n"
                "Code instructor\n"
                "Ischool\n"
                "06/2024\n"
                "Coding instructor for an MCIT education project."
            )
        )

        self.assertEqual(
            [entry.head(3) for entry in entries],
            [
                "DevOps Engineer | Cloud4Rain | 12/2024 – present",
                "IT Administration | Faculty of Artificial Intelligence, Badr University, Assiut | 01/2024 – 12/2024",
                "Teaching assistant | Faculty of Artificial Intelligence, Badr University, Assiut | 01/2024 – 12/2024",
                "Code instructor | Ischool | 06/2024",
            ],
        )
        professional_entries = [entry for entry in entries if is_experience_entry(entry)]
        self.assertNotIn(
            "Teaching assistant",
            [entry.head(1) for entry in professional_entries],
        )

        roles, _, ambiguity = compute_devops_roles(professional_entries)
        self.assertFalse(ambiguity)
        self.assertEqual(
            [(role.title, role.company) for role in roles],
            [
                (
                    "IT Administration",
                    "Faculty of Artificial Intelligence, Badr University, Assiut",
                ),
                ("DevOps Engineer", "Cloud4Rain"),
            ],
        )

    def test_wrapped_responsibility_is_not_stolen_as_next_company(self) -> None:
        entries = build_date_based_entries_from_lines(
            self.lines(
                "Senior DevOps Engineer\n"
                "Jan 2025 – now\n"
                "Fixed Misr (FEDIS) - Cairo\n"
                "Maintain visibility and anticipate failures to ensure\n"
                "smoother operations with less downtime.\n"
                "DevOps Engineer\n"
                "July 2023 – Jan 2025\n"
                "Fixed Misr (FEDIS) - Cairo\n"
                "Deploy applications using Kubernetes, Helm, and Docker."
            )
        )

        self.assertEqual(len(entries), 2)
        self.assertEqual(
            entries[0].lines[-1][1],
            "smoother operations with less downtime.",
        )
        self.assertNotIn(
            "smoother operations with less downtime.",
            entries[1].text(),
        )

        roles, _, ambiguity = compute_devops_roles(entries)
        self.assertFalse(ambiguity)
        self.assertEqual(
            [(role.title, role.company) for role in roles],
            [
                ("DevOps Engineer", "Fixed Misr (FEDIS) - Cairo"),
                ("Senior DevOps Engineer", "Fixed Misr (FEDIS) - Cairo"),
            ],
        )

    def test_customer_support_responsibility_is_not_company_or_devops_tenure(
        self,
    ) -> None:
        entries = build_date_based_entries_from_lines(
            self.lines(
                "IBM\n"
                "Linux and OpenShift Support Engineer\n"
                "Jan 2022 — Present\n"
                "- Provide remote technical support assistance to clients.\n"
                "Customer Success Manager\n"
                "Nov 2021 — Present\n"
                "- Being client point of contact when an issue arises\n"
                "Huawei\n"
                "Customer Support Engineer\n"
                "Nov 2020 — Nov 2021\n"
                "- Providing support for Huawei revenue management applications.\n"
                "- Providing support for the OS hosting Huawei applications, "
                "especially SuSE Linux.\n"
                "- Providing support for Oracle Database and cluster software."
            )
        )

        huawei_entry = next(
            entry for entry in entries if "Customer Support Engineer" in entry.text()
        )
        self.assertEqual(
            _entry_role_identity(huawei_entry),
            ("Customer Support Engineer", "Huawei"),
        )

        roles, total_months, ambiguity = compute_devops_roles(entries)

        self.assertFalse(ambiguity)
        self.assertEqual(
            [(role.title, role.company) for role in roles],
            [("Linux and OpenShift Support Engineer", "IBM")],
        )
        self.assertEqual(total_months, roles[0].months_added)

    def test_dates_and_role_words_inside_bullets_do_not_create_jobs(self) -> None:
        description_with_dates = (
            "•Installing and troubleshooting Windows servers "
            "(2003 - 2008 - 2012) and desktop Windows."
        )
        entries = build_date_based_entries_from_lines(
            self.lines(
                "Linux Administrator, Variiance\n"
                "11/2020 – 03/2022\n"
                f"{description_with_dates}\n"
                "•Installing tools such as Prometheus, Grafana, and VoIP "
                "software. Linux Administrator\n"
                "•Fault finding and logging performance exceptions.\n"
                "IT Specialist, Zack's\n"
                "02/2020 – 11/2020\n"
                "•Managed computers and network infrastructure."
            )
        )

        self.assertFalse(is_date_range_line(description_with_dates))
        self.assertEqual(len(entries), 2)
        self.assertIn(description_with_dates, entries[0].text())

        roles, _, ambiguity = compute_devops_roles(entries)
        self.assertFalse(ambiguity)
        self.assertNotIn(2003, [role.start.year for role in roles])
        self.assertEqual(
            [
                (role.title, role.company, role.start, role.end)
                for role in roles
                if role.title == "Linux Administrator"
            ],
            [
                (
                    "Linux Administrator",
                    "Variiance",
                    dt.date(2020, 11, 1),
                    dt.date(2022, 3, 1),
                )
            ],
        )

    def test_role_titles_on_both_sides_of_one_date_are_layout_ambiguity(self) -> None:
        entries = build_date_based_entries_from_lines(
            self.lines(
                "Devops Engineer 2\n"
                "Aug 2023 - Present\n"
                "Teacher Assistant\n"
                "Oct 2020 - Jan 2021\n"
                "Alexandria University\n"
                "Eventum Solutions"
            )
        )
        roles, _, _ = compute_devops_roles(entries)

        self.assertTrue(has_experience_layout_anomaly(entries, roles))

    def test_training_provider_under_work_experience_is_not_counted(self) -> None:
        entries = build_date_based_entries_from_lines(
            self.lines(
                "DevOps Engineer\n"
                "\n"
                "Feb 2025 - Present\n"
                "Blnk Fintech Company, Cairo\n"
                "• Managed production Linux infrastructure.\n"
                "\n"
                "NTI\n"
                "Sep 2024 - Dec 2024\n"
                "DevOps Accelerator Track, Nasr City, Cairo\n"
                "• Worked with AWS and Kubernetes during training.\n"
                "\n"
                "DevOps Engineer\n"
                "\n"
                "Apr 2024 - Jul 2024\n"
                "E-Finance Group, Cairo\n"
                "• Automated deployments with Jenkins."
            )
        )

        self.assertEqual(len(entries), 3)
        self.assertEqual(
            [entry.head(3) for entry in entries],
            [
                "DevOps Engineer | Feb 2025 - Present | Blnk Fintech Company, Cairo",
                "NTI | Sep 2024 - Dec 2024 | DevOps Accelerator Track, Nasr City, Cairo",
                "DevOps Engineer | Apr 2024 - Jul 2024 | E-Finance Group, Cairo",
            ],
        )
        self.assertEqual(
            [is_education_program(entry.head(3)) for entry in entries],
            [False, True, False],
        )

        roles, _, _ = compute_devops_roles(entries)
        self.assertEqual([role.title for role in roles], ["DevOps Engineer"] * 2)
        self.assertEqual(
            [role.company for role in roles],
            ["E-Finance Group, Cairo", "Blnk Fintech Company, Cairo"],
        )
        self.assertNotIn(
            "DevOps Accelerator Track, Nasr City, Cairo",
            [role.title for role in roles],
        )

    def test_company_role_single_month_layout_stays_in_one_entry(self) -> None:
        entries = build_date_based_entries_from_lines(
            self.lines(
                "• Sprints\n"
                "Cairo, Egypt\n"
                "Student Ambassador\n"
                "April 2025 - Present\n"
                "◦ Leadership & Partnerships: Led community initiatives.\n"
                "• Banque Misr – Rowad Internship Program\n"
                "Cairo, Egypt\n"
                "DevOps Intern\n"
                "August 2024\n"
                "◦ Infrastructure & CI/CD: Automated deployment pipelines using "
                "Jenkins, Docker, and Kubernetes."
            )
        )

        self.assertEqual(len(entries), 2)
        self.assertEqual(
            entries[0].head(4),
            "• Sprints | Cairo, Egypt | Student Ambassador | April 2025 - Present",
        )
        self.assertEqual(
            entries[1].head(4),
            "• Banque Misr – Rowad Internship Program | Cairo, Egypt | "
            "DevOps Intern | August 2024",
        )
        self.assertTrue(is_education_program(entries[0].head(3)))

        roles, total_months, ambiguity = compute_devops_roles(entries)
        self.assertFalse(ambiguity)
        self.assertEqual(total_months, 1)
        self.assertEqual(len(roles), 1)
        self.assertEqual(roles[0].title, "DevOps Intern")
        self.assertEqual(
            roles[0].company,
            "Banque Misr – Rowad Internship Program",
        )
        self.assertEqual(roles[0].start, dt.date(2024, 8, 1))
        self.assertEqual(roles[0].end, dt.date(2024, 8, 1))
        self.assertEqual(roles[0].months_added, 1)

    def test_comma_separates_role_from_single_word_company(self) -> None:
        entries = build_date_based_entries_from_lines(
            self.lines(
                "DevOps Engineer, Blnk\n"
                "Jul 2023 - Mar 2024\n"
                "• Built and managed private clouds using OpenStack.\n"
                "DevOps Engineer Intern, Konecta\n"
                "Jul 2025 - Nov 2025\n"
                "• Built CI/CD pipelines with Jenkins and GitHub Actions."
            )
        )

        roles, _, _ = compute_devops_roles(entries)
        self.assertEqual(
            [(role.title, role.company) for role in roles],
            [
                ("DevOps Engineer", "Blnk"),
                ("DevOps Engineer Intern", "Konecta"),
            ],
        )

    def test_company_wrapped_around_dates_is_not_replaced_by_prose(self) -> None:
        entries = build_date_based_entries_from_lines(
            self.lines(
                "Ericsson (2021-Current)\n"
                "Cloud solution architect Engineer\n"
                "Analyzing, designing, and developing commercially viable solutions.\n"
                "Provide technical support and input to the delivery team.\n"
                "Ericsson (2019-2021)\n"
                "Cloud Integration Engineer\n"
                "Plan the implementation of the product configuration for NFVI.\n"
                "Execute product configuration and integration work."
            )
        )

        roles, _, ambiguity = compute_devops_roles(entries)
        self.assertFalse(ambiguity)
        self.assertEqual(
            [(role.title, role.company) for role in roles],
            [
                ("Cloud Integration Engineer", "Ericsson"),
                ("Cloud solution architect Engineer", "Ericsson"),
            ],
        )
        self.assertEqual(roles[0].start, dt.date(2019, 1, 1))
        self.assertEqual(roles[0].end, dt.date(2021, 12, 1))
        self.assertEqual(roles[1].start, dt.date(2021, 1, 1))
        self.assertEqual(roles[1].end, dt.date.today())


if __name__ == "__main__":
    unittest.main()
