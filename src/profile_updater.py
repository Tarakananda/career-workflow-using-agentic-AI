"""
Naukri Profile Auto-Updater
Updates Naukri profile with optimized content using existing session cookies
Only modifies: Summary, Key Skills, Projects
Preserves: Personal details, Certifications, Education, Experience
"""
from pathlib import Path
from typing import Any, Optional
import json
import yaml
from datetime import datetime
from playwright.sync_api import sync_playwright
from playwright_stealth.stealth import Stealth


# Optimized Profile Content
OPTIMIZED_SUMMARY = """Cloud & DevOps Engineer with 3+ years of hands-on experience designing, implementing, and operating cloud-native infrastructure across AWS, Azure, and GCP. Expert in Kubernetes (EKS/AKS/GKE), Terraform/Terragrunt, GitOps (Argo CD/Flux), and CI/CD automation using Jenkins, GitHub Actions, and GitLab CI.

Core Achievements:
- Built multi-cloud CI/CD platforms reducing deployment time by 60% using Terraform, Argo CD, and Helm
- Implemented GitOps workflows with Argo CD/Flux managing 50+ microservices across 3 environments
- Designed observability stacks (Prometheus/Grafana/Loki/Tempo/Datadog) cutting MTTR by 40%
- Automated infrastructure provisioning with Terraform/Terragrunt managing 200+ resources
- Established container security pipelines with Trivy, Cosign, and Kyverno reducing vulnerabilities by 70%
- Optimized cloud costs using FinOps practices (Kubecost, AWS Compute Optimizer) saving 25% monthly spend

Tech Stack: AWS (EKS, Lambda, ECS, RDS, CloudFormation), Azure (AKS, Functions, DevOps, Key Vault), GCP (GKE, Cloud Run, Cloud Build), Kubernetes, Helm, Kustomize, Argo CD, Flux, Terraform, Terragrunt, Jenkins, GitHub Actions, GitLab CI, Python, Go, Bash, Prometheus, Grafana, Loki, Tempo, Datadog, Trivy, Vault, Istio.

Certifications: AZ-900, AI-900 | Pursuing: AWS SAA, AZ-104, CKAD, Terraform Associate
Availability: Immediate | Location: Hyderabad / Bengaluru (Hybrid/Remote) | Notice: 3 months (negotiable)"""

OPTIMIZED_KEY_SKILLS = [
    "Kubernetes (EKS/AKS/GKE)",
    "Terraform / Terragrunt",
    "AWS (EC2, VPC, EKS, Lambda, RDS, CloudFormation)",
    "Azure (AKS, Functions, DevOps, Key Vault)",
    "GCP (GKE, Cloud Run, Cloud Build)",
    "Docker / Containerization",
    "CI/CD (Jenkins, GitHub Actions, GitLab CI, Azure DevOps)",
    "GitOps (Argo CD, Flux v2)",
    "Helm / Kustomize / Helmfile",
    "Infrastructure as Code (Terraform, CloudFormation, Pulumi awareness)",
    "Prometheus / Grafana / Loki / Tempo",
    "Datadog / CloudWatch / ELK Stack",
    "Python (boto3, automation, scripting)",
    "Go (basics, operators)",
    "Bash / Shell Scripting",
    "Ansible / Configuration Management",
    "Trivy / SonarQube / Container Security",
    "HashiCorp Vault / AWS Secrets Manager / Azure Key Vault",
    "Service Mesh (Istio basics, mTLS)",
    "Git / GitHub / GitLab / Bitbucket",
    "Linux / System Administration",
    "Networking (VPC, ALB, Route 53, VPN, DNS)",
    "Databases (RDS, DynamoDB, PostgreSQL, Redis)",
    "Monitoring & Alerting (Alertmanager, PagerDuty)",
    "Cost Optimization (FinOps, Kubecost, Compute Optimizer)",
    "Disaster Recovery / Backup (Velero, Cross-region)",
    "Incident Management / RCA / On-call",
    "Agile / Scrum / Jira / Confluence"
]

OPTIMIZED_PROJECTS = [
    {
        "name": "Multi-Cloud CI/CD Automation Platform",
        "description": "Designed and implemented end-to-end CI/CD platform across AWS and Azure managing 50+ microservices. Integrated GitHub Actions for build/test, Terraform for infrastructure provisioning, Argo CD for GitOps deployments. Reduced deployment time from 45 min to 12 min (73% improvement) with 99.9% deployment success rate. Implemented automated rollback, canary deployments, and policy enforcement with Kyverno/OPA.",
        "tech_stack": "AWS, Azure, Terraform, Jenkins, GitHub Actions, Argo CD, Helm, Kubernetes, Docker"
    },
    {
        "name": "Highly Available Three-Tier AWS Application Deployment",
        "description": "Architected HA three-tier web app with multi-AZ VPC, public/private subnets, NAT Gateways. Implemented ALB with target groups, Auto Scaling (3-50 instances), Multi-AZ RDS with read replicas. Configured Route 53 health checks, S3 static hosting with CloudFront CDN, SSL/TLS via ACM. Achieved 99.99% uptime with automated failover, CloudWatch monitoring, and SNS alerting.",
        "tech_stack": "AWS (VPC, EC2, ALB, ASG, RDS, Route 53, S3, CloudWatch, IAM, CloudFormation)"
    },
    {
        "name": "Azure Multi-Region Infrastructure with GitOps",
        "description": "Built multi-region Azure infrastructure (East US, West Europe) with VNet peering and global Traffic Manager. Implemented Flux v2 GitOps with Kustomize overlays for 100+ microservices across environments. Configured Azure Key Vault for secrets, Azure Monitor for observability, Private Endpoints for security. Validated regional failover <30 seconds, achieving 40% cost savings vs single-region deployment.",
        "tech_stack": "Azure (AKS, VNet, Load Balancer, Traffic Manager, Key Vault), Terraform, Flux v2, Helm"
    },
    {
        "name": "Observability Stack with GitOps",
        "description": "Deployed full observability stack via Helm/Argo CD: metrics, logs, traces unified in Grafana. Integrated Datadog APM for distributed tracing, correlated with logs/metrics reducing MTTR by 40%. Implemented 500+ custom dashboards, 200+ alerts with Alertmanager/PagerDuty routing. Process 50GB logs/day, 1M+ metrics/sec with 99.9% query availability.",
        "tech_stack": "Prometheus, Grafana, Loki, Tempo, Alertmanager, Datadog, Kubernetes, Helm, Argo CD"
    },
    {
        "name": "Serverless Event-Driven Architecture",
        "description": "Built event-driven order processing pipeline handling 1M+ events/day with 99.9% reliability. Replaced EC2-based workers with Lambda + Step Functions reducing compute costs by 90%. Implemented dead-letter queues, retry policies, and X-Ray tracing for observability. Achieved sub-second latency with auto-scaling, zero operational overhead.",
        "tech_stack": "AWS Lambda, EventBridge, SQS, SNS, Step Functions, API Gateway, DynamoDB, CloudWatch"
    }
]


class NaukriProfileUpdater:
    def __init__(self, session_file: Path = Path("session.json")):
        self.session_file = session_file
        self.cookies = self._load_cookies()
        
    def _load_cookies(self) -> Optional[list]:
        if not self.session_file.exists():
            return None
        with open(self.session_file, encoding="utf-8") as f:
            cookies = json.load(f)
        return cookies if isinstance(cookies, list) and len(cookies) > 0 else None
    
    def _backup_current_profile(self, page: Any) -> dict:
        """Extract and backup current profile data"""
        print("  Backing up current Naukri profile...")
        
        # Navigate to profile page
        page.goto("https://www.naukri.com/mnjuser/profile", wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(3000)
        
        profile_data = {
            "backup_timestamp": datetime.now().isoformat(),
            "summary": "",
            "key_skills": [],
            "projects": [],
            "certifications": [],
            "experience": [],
            "education": []
        }
        
        try:
            # Try to extract summary
            summary_selectors = [
                "[data-testid='profile-summary']",
                ".profile-summary",
                "[class*='summary']",
                "textarea[name*='summary']",
                "#summary"
            ]
            for sel in summary_selectors:
                elem = page.query_selector(sel)
                if elem and elem.is_visible():
                    profile_data["summary"] = elem.inner_text().strip() or elem.get_attribute("value") or ""
                    break
        except Exception as e:
            print(f"  Could not extract summary: {e}")
        
        try:
            # Try to extract key skills
            skill_selectors = [
                "[data-testid='key-skills']",
                ".key-skills",
                "[class*='key-skill']",
                "input[name*='skill']",
                ".skill-tag"
            ]
            for sel in skill_selectors:
                elems = page.query_selector_all(sel)
                for el in elems:
                    text = el.inner_text().strip() or el.get_attribute("value") or ""
                    if text and len(text) > 2:
                        profile_data["key_skills"].append(text)
        except Exception as e:
            print(f"  Could not extract skills: {e}")
        
        # Save backup
        backup_dir = Path("naukri_backups")
        backup_dir.mkdir(exist_ok=True)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_file = backup_dir / f"naukri_profile_backup_{timestamp}.json"
        
        with open(backup_file, "w") as f:
            json.dump(profile_data, f, indent=2, ensure_ascii=False)
        
        print(f"  Profile backed up to: {backup_file}")
        return profile_data
    
    def update_profile(self, headless: bool = False) -> bool:
        """Main method to update Naukri profile"""
        if not self.cookies:
            print("  No valid session. Run login.py first.")
            return False
        
        print("=" * 60)
        print("NAUKRI PROFILE UPDATER")
        print("=" * 60)
        print("This will update: Summary, Key Skills, Projects")
        print("This will NOT change: Personal details, Certifications, Education, Experience")
        print("=" * 60)
        
        with sync_playwright() as p:
            Stealth().use_sync(p)
            browser = p.chromium.launch(headless=headless)
            context = browser.new_context()
            context.add_cookies(self.cookies)
            page = context.new_page()
            
            try:
                # Backup current profile
                self._backup_current_profile(page)
                
                # Update summary
                self._update_summary(page)
                
                # Update key skills
                self._update_key_skills(page)
                
                # Update projects
                self._update_projects(page)
                
                print("\n" + "=" * 60)
                print("PROFILE UPDATE COMPLETE!")
                print("Please verify the changes on Naukri manually.")
                print("=" * 60)
                return True
                
            except Exception as e:
                print(f"\nError during profile update: {e}")
                return False
            finally:
                browser.close()
    
    def _update_summary(self, page: Any) -> bool:
        """Update profile summary"""
        print("\nUpdating profile summary...")
        
        try:
            page.goto("https://www.naukri.com/mnjuser/profile", wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(3000)
            
            # Find and click edit summary button
            edit_selectors = [
                "button:has-text('Edit') >> near :text('Summary')",
                "button:has-text('Edit') >> near :text('Profile Summary')",
                "[data-testid='edit-summary']",
                "button.edit-summary",
                "a:has-text('Edit') >> near :text('Summary')"
            ]
            
            clicked = False
            for sel in edit_selectors:
                try:
                    btn = page.query_selector(sel)
                    if btn and btn.is_visible():
                        btn.click()
                        page.wait_for_timeout(2000)
                        clicked = True
                        break
                except Exception:
                    continue
            
            if not clicked:
                print("  Could not find edit summary button, trying alternative approach...")
                # Try double-click on summary area
                summary_area = page.query_selector(":text('Summary') >> .. >> textarea, :text('Profile Summary') >> .. >> textarea")
                if summary_area:
                    summary_area.dblclick()
                    page.wait_for_timeout(1000)
                    clicked = True
            
            if clicked:
                # Find textarea and fill
                textarea_selectors = [
                    "textarea[name*='summary']",
                    "textarea[placeholder*='summary' i]",
                    "textarea[placeholder*='profile' i]",
                    "#summary",
                    ".profile-summary textarea",
                    "[data-testid='summary-textarea']"
                ]
                
                for sel in textarea_selectors:
                    textarea = page.query_selector(sel)
                    if textarea and textarea.is_visible():
                        textarea.fill(OPTIMIZED_SUMMARY)
                        page.wait_for_timeout(1000)
                        print("  Summary filled successfully")
                        break
                
                # Save
                save_selectors = [
                    "button:has-text('Save')",
                    "button:has-text('Update')",
                    "button[type='submit']",
                    "[data-testid='save-summary']"
                ]
                for sel in save_selectors:
                    btn = page.query_selector(sel)
                    if btn and btn.is_visible():
                        btn.click()
                        page.wait_for_timeout(3000)
                        print("  Summary saved")
                        return True
            
            print("  Could not update summary - manual update may be needed")
            return False
            
        except Exception as e:
            print(f"  Error updating summary: {e}")
            return False
    
    def _update_key_skills(self, page: Any) -> bool:
        """Update key skills"""
        print("\nUpdating key skills...")
        
        try:
            page.goto("https://www.naukri.com/mnjuser/profile", wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(3000)
            
            # Find and click edit skills
            edit_selectors = [
                "button:has-text('Edit') >> near :text('Key Skill')",
                "button:has-text('Edit') >> near :text('Skills')",
                "[data-testid='edit-skills']",
                "button.edit-skills"
            ]
            
            clicked = False
            for sel in edit_selectors:
                try:
                    btn = page.query_selector(sel)
                    if btn and btn.is_visible():
                        btn.click()
                        page.wait_for_timeout(2000)
                        clicked = True
                        break
                except Exception:
                    continue
            
            if clicked:
                # Try to find skill input fields
                # Naukri typically has an input where you type and select from dropdown
                for i, skill in enumerate(OPTIMIZED_KEY_SKILLS):
                    try:
                        # Find skill input
                        skill_input = page.query_selector(
                            "input[placeholder*='skill' i], "
                            "input[name*='skill' i], "
                            ".skill-input, "
                            "[data-testid='skill-input']"
                        )
                        if skill_input and skill_input.is_visible():
                            skill_input.fill(skill)
                            page.wait_for_timeout(1000)
                            # Press Enter or select from dropdown
                            skill_input.press("Enter")
                            page.wait_for_timeout(500)
                            print(f"  Added skill {i+1}/{len(OPTIMIZED_KEY_SKILLS)}: {skill}")
                        else:
                            # Try clicking "Add Skill" button first
                            add_btn = page.query_selector("button:has-text('Add Skill'), button:has-text('Add')")
                            if add_btn and add_btn.is_visible():
                                add_btn.click()
                                page.wait_for_timeout(1000)
                                skill_input = page.query_selector("input[placeholder*='skill' i]")
                                if skill_input:
                                    skill_input.fill(skill)
                                    skill_input.press("Enter")
                                    page.wait_for_timeout(500)
                                    print(f"  Added skill {i+1}/{len(OPTIMIZED_KEY_SKILLS)}: {skill}")
                    except Exception as e:
                        print(f"  Could not add skill '{skill}': {e}")
                        continue
                
                # Save skills
                save_selectors = [
                    "button:has-text('Save')",
                    "button:has-text('Update')",
                    "button[type='submit']"
                ]
                for sel in save_selectors:
                    btn = page.query_selector(sel)
                    if btn and btn.is_visible():
                        btn.click()
                        page.wait_for_timeout(3000)
                        print("  Skills saved")
                        return True
            
            print("  Could not update skills - manual update may be needed")
            return False
            
        except Exception as e:
            print(f"  Error updating skills: {e}")
            return False
    
    def _update_projects(self, page: Any) -> bool:
        """Update projects"""
        print("\nUpdating projects...")
        
        try:
            page.goto("https://www.naukri.com/mnjuser/profile", wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(3000)
            
            # Find and click edit projects
            edit_selectors = [
                "button:has-text('Edit') >> near :text('Project')",
                "[data-testid='edit-projects']",
                "button.edit-projects"
            ]
            
            clicked = False
            for sel in edit_selectors:
                try:
                    btn = page.query_selector(sel)
                    if btn and btn.is_visible():
                        btn.click()
                        page.wait_for_timeout(2000)
                        clicked = True
                        break
                except Exception:
                    continue
            
            if clicked:
                for i, proj in enumerate(OPTIMIZED_PROJECTS):
                    try:
                        # Click add project
                        add_btn = page.query_selector("button:has-text('Add Project'), button:has-text('Add')")
                        if add_btn and add_btn.is_visible():
                            add_btn.click()
                            page.wait_for_timeout(1500)
                        
                        # Fill project name
                        name_input = page.query_selector("input[placeholder*='project name' i], input[name*='project' i], input[placeholder*='title' i]")
                        if name_input and name_input.is_visible():
                            name_input.fill(proj["name"])
                            page.wait_for_timeout(500)
                        
                        # Fill description
                        desc_input = page.query_selector("textarea[placeholder*='description' i], textarea[name*='description' i], textarea[placeholder*='detail' i]")
                        if desc_input and desc_input.is_visible():
                            desc_input.fill(proj["description"])
                            page.wait_for_timeout(500)
                        
                        # Fill tech stack
                        tech_input = page.query_selector("input[placeholder*='technology' i], input[placeholder*='tech' i], input[name*='technology' i]")
                        if tech_input and tech_input.is_visible():
                            tech_input.fill(proj["tech_stack"])
                            page.wait_for_timeout(500)
                        
                        # Save project
                        save_btn = page.query_selector("button:has-text('Save'), button:has-text('Add Project'), button[type='submit']")
                        if save_btn and save_btn.is_visible():
                            save_btn.click()
                            page.wait_for_timeout(2000)
                            print(f"  Added project {i+1}/{len(OPTIMIZED_PROJECTS)}: {proj['name']}")
                        else:
                            print(f"  Could not find save button for project {proj['name']}")
                    except Exception as e:
                        print(f"  Could not add project '{proj['name']}': {e}")
                        continue
                
                print("  Projects update attempted")
                return True
            
            print("  Could not update projects - manual update may be needed")
            return False
            
        except Exception as e:
            print(f"  Error updating projects: {e}")
            return False


def update_naukri_profile(session_file: Path = Path("session.json"), headless: bool = False) -> bool:
    """Entry point to update Naukri profile"""
    updater = NaukriProfileUpdater(session_file)
    return updater.update_profile(headless)


if __name__ == "__main__":
    import sys
    headless = "--headless" in sys.argv
    success = update_naukri_profile(headless=headless)
    sys.exit(0 if success else 1)