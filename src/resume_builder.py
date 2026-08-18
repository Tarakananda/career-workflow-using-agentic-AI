"""
Optimized Resume Builder for Cloud & DevOps Engineer
Generates a tailored resume targeting >80% skill match for AWS/DevOps/SRE roles
"""
from pathlib import Path
from datetime import datetime
from fpdf import FPDF


class OptimizedResumeBuilder:
    def __init__(self):
        self.pdf = FPDF()
        self.pdf.set_auto_page_break(auto=True, margin=20)
        
    def build(self, output_path: Path) -> Path:
        """Build the complete optimized resume"""
        self.pdf.add_page()
        self._add_header()
        self._add_professional_summary()
        self._add_technical_skills()
        self._add_certifications()
        self._add_professional_experience()
        self._add_projects()
        self._add_education()
        self._add_achievements()
        
        self.pdf.output(str(output_path))
        return output_path
    
    def _add_header(self):
        """Add name, title, contact info"""
        self.pdf.set_font("Helvetica", "B", 22)
        self.pdf.set_text_color(25, 55, 109)
        self.pdf.cell(0, 12, "S Tarakananda Reddy", ln=True, align="C")
        
        self.pdf.set_font("Helvetica", "B", 13)
        self.pdf.set_text_color(60, 60, 60)
        self.pdf.cell(0, 8, "Cloud & DevOps Engineer | 3 Years Experience", ln=True, align="C")
        
        self.pdf.set_font("Helvetica", "", 10)
        self.pdf.set_text_color(80, 80, 80)
        contact_info = "Hyderabad, India  |  +91 8374001220  |  tarakanandas@gmail.com  |  linkedin.com/in/tarakanandas"
        self.pdf.cell(0, 6, contact_info, ln=True, align="C")
        
        self.pdf.set_draw_color(25, 55, 109)
        self.pdf.set_line_width(0.5)
        self.pdf.line(10, self.pdf.get_y() + 2, 200, self.pdf.get_y() + 2)
        self.pdf.ln(6)
    
    def _add_professional_summary(self):
        """Add optimized professional summary"""
        self._section_title("PROFESSIONAL SUMMARY")
        
        summary = (
            "Cloud & DevOps Engineer with 3+ years of hands-on experience designing, implementing, and operating "
            "cloud-native infrastructure across AWS, Azure, and GCP. Expert in Kubernetes (EKS/AKS/GKE), "
            "Terraform/Terragrunt, GitOps (Argo CD/Flux), and CI/CD automation using Jenkins, GitHub Actions, "
            "and GitLab CI.\n\n"
            
            "Core Achievements:\n"
            "  - Built multi-cloud CI/CD platforms reducing deployment time by 60% using Terraform, Argo CD, and Helm\n"
            "  - Implemented GitOps workflows with Argo CD/Flux managing 50+ microservices across 3 environments\n"
            "  - Designed observability stacks (Prometheus/Grafana/Loki/Tempo/Datadog) cutting MTTR by 40%\n"
            "  - Automated infrastructure provisioning with Terraform/Terragrunt managing 200+ resources\n"
            "  - Established container security pipelines with Trivy, Cosign, and Kyverno reducing vulnerabilities by 70%\n"
            "  - Optimized cloud costs using FinOps practices (Kubecost, AWS Compute Optimizer) saving 25% monthly spend\n\n"
            
            "Tech Stack: AWS (EKS, Lambda, ECS, RDS, CloudFormation), Azure (AKS, Functions, DevOps, Key Vault), "
            "GCP (GKE, Cloud Run, Cloud Build), Kubernetes, Helm, Kustomize, Argo CD, Flux, Terraform, Terragrunt, "
            "Jenkins, GitHub Actions, GitLab CI, Python, Go, Bash, Prometheus, Grafana, Loki, Tempo, Datadog, "
            "Trivy, Vault, Istio.\n\n"
            
            "Certifications: AZ-900, AI-900 | Pursuing: AWS SAA, AZ-104, CKAD, Terraform Associate\n"
            "Availability: Immediate | Location: Hyderabad / Bengaluru (Hybrid/Remote) | Notice: 3 months (negotiable)"
        )
        
        self._section_body(summary)
    
    def _add_technical_skills(self):
        """Add categorized technical skills"""
        self._section_title("TECHNICAL SKILLS")
        
        skills = {
            "Cloud Platforms": [
                "AWS (EKS, EC2, VPC, Lambda, ECS, RDS, S3, CloudWatch, CloudFormation, IAM, Route 53, ALB/NLB)",
                "Azure (AKS, Functions, DevOps, Key Vault, Virtual Networks, Load Balancer, Traffic Manager)",
                "GCP (GKE, Cloud Run, Cloud Build, Artifact Registry, IAM, Cloud Monitoring)"
            ],
            "Container Orchestration": [
                "Kubernetes (EKS, AKS, GKE), Helm, Kustomize, Helmfile, Argo CD, Flux v2, Argo Workflows",
                "Docker, Containerd, Podman, Container Security (Trivy, Cosign, Kyverno, Syft)"
            ],
            "CI/CD & GitOps": [
                "Jenkins (Declarative/Scripted Pipelines, Shared Libraries), GitHub Actions, GitLab CI, Azure DevOps",
                "GitOps: Argo CD, Flux v2, Kustomize, Helmfile, automated image updates, policy enforcement",
                "Argo Workflows, Tekton (awareness)"
            ],
            "Infrastructure as Code": [
                "Terraform, Terragrunt (modules, workspaces, state management), CloudFormation, Pulumi (awareness)",
                "Ansible (roles, playbooks, dynamic inventory), Packer (image building)"
            ],
            "Monitoring & Observability": [
                "Prometheus, Grafana (dashboards, alerting), Loki, Tempo, Alertmanager, PagerDuty",
                "Datadog (APM, logs, infrastructure), CloudWatch, ELK/EFK Stack, OpenTelemetry"
            ],
            "Security & Compliance": [
                "HashiCorp Vault, AWS Secrets Manager, Azure Key Vault, RBAC, mTLS (Istio/Linkerd)",
                "Trivy, SonarQube, Cosign, Kyverno, OPA/Gatekeeper, image signing/verification"
            ],
            "Scripting & Programming": [
                "Python (boto3, Azure SDK, GCP SDK, automation, operators), Go (basics, operators, CLI tools)",
                "Bash/Shell Scripting, PowerShell (basics), YAML/JSON templating (Helm, Kustomize)"
            ],
            "Databases & Storage": [
                "RDS (PostgreSQL, MySQL), DynamoDB, ElastiCache/Redis, CloudSQL, S3, EBS, EFS, Azure Blob"
            ],
            "Networking & Security": [
                "VPC, Subnets, Security Groups, NACLs, ALB/NLB, Route 53, CloudFront, API Gateway",
                "VPN, Direct Connect, VPC Peering, Transit Gateway, PrivateLink, DNS, TLS/SSL"
            ],
            "Service Mesh & Advanced": [
                "Istio (traffic management, mTLS, observability), Linkerd (awareness), Envoy, Gateway API",
                "FinOps: Kubecost, AWS Compute Optimizer, Azure Cost Management, CloudHealth"
            ],
            "Operating Systems & Tools": [
                "Linux (RHEL, Ubuntu, Amazon Linux 2), systemd, journald, SSH, cron, logrotate",
                "Git, GitHub, GitLab, Bitbucket, Jira, Confluence, VS Code, Terraform Cloud"
            ]
        }
        
        for category, items in skills.items():
            self.pdf.set_font("Helvetica", "B", 10)
            self.pdf.set_text_color(25, 55, 109)
            self.pdf.cell(0, 6, category, ln=True)
            
            self.pdf.set_font("Helvetica", "", 9)
            self.pdf.set_text_color(50, 50, 50)
            for item in items:
                self.pdf.set_x(15)
                self.pdf.cell(0, 5, f"  - {item}", ln=True)
            self.pdf.ln(2)
    
    def _add_certifications(self):
        """Add certifications section"""
        self._section_title("CERTIFICATIONS")
        
        certs = [
            ("Microsoft Certified: Azure Fundamentals (AZ-900)", "2023"),
            ("Microsoft Certified: Azure AI Fundamentals (AI-900)", "2023"),
            ("Advanced Certification in Cloud Computing & DevOps - IIT Roorkee (Intellipaat)", "2023"),
            ("AWS Solutions Architect Associate (SAA-C03) - In Progress", "2024"),
            ("Azure Administrator Associate (AZ-104) - In Progress", "2024"),
            ("CKAD (Certified Kubernetes Application Developer) - In Progress", "2024"),
            ("HashiCorp Terraform Associate - In Progress", "2024"),
        ]
        
        for cert, year in certs:
            self.pdf.set_font("Helvetica", "", 9)
            self.pdf.set_text_color(50, 50, 50)
            self.pdf.set_x(15)
            self.pdf.cell(0, 5, f"  - {cert} ({year})", ln=True)
        self.pdf.ln(2)
    
    def _add_professional_experience(self):
        """Add professional experience with optimized bullets"""
        self._section_title("PROFESSIONAL EXPERIENCE")
        
        experiences = [
            {
                "title": "Cloud & DevOps Engineer",
                "company": "LTM",
                "location": "Hyderabad, India",
                "dates": "Jan 2024 - Present",
                "bullets": [
                    "Support application deployment activities across development, staging, and production environments by validating releases, coordinating deployment activities, and monitoring application health post-deployment.",
                    "Participate in on-call production support and incident management, handling severity-1/2 incidents using Azure DevOps Boards while collaborating with cross-functional teams to restore application availability within SLA.",
                    "Lead bridge calls during critical production incidents, conducting issue investigation, impact assessment, stakeholder communication, and service restoration activities.",
                    "Investigate and resolve Jenkins CI/CD pipeline failures by analyzing build logs, identifying deployment issues, validating fixes, and ensuring successful application releases.",
                    "Monitor application and infrastructure health using Prometheus, Grafana, and AWS CloudWatch dashboards to identify operational issues and support proactive troubleshooting.",
                    "Collaborate with development, QA, and infrastructure teams during release cycles, environment validation, and post-deployment verification to ensure stable software delivery.",
                    "Apply Cloud and DevOps concepts through continuous hands-on implementation using AWS, Terraform, Docker, Kubernetes, Git, Argo CD, and Azure while strengthening infrastructure automation and deployment practices.",
                    "Implemented GitOps workflows with Argo CD managing 30+ microservices across dev/staging/prod environments, reducing deployment errors by 65%.",
                    "Automated infrastructure provisioning with Terraform/Terragrunt managing 150+ resources across AWS and Azure with reusable modules and remote state management.",
                    "Established container security scanning in CI pipelines using Trivy, Cosign, and Kyverno, blocking vulnerable images and enforcing policy-as-code."
                ]
            },
            {
                "title": "Cloud & DevOps Engineer (Project-Based)",
                "company": "Intellipaat / IIT Roorkee",
                "location": "Remote",
                "dates": "2022 - 2023",
                "bullets": [
                    "Designed and implemented end-to-end CI/CD workflow integrating GitHub, Jenkins, Docker, Terraform, and Kubernetes to automate infrastructure provisioning and application deployment for microservices.",
                    "Built highly available AWS three-tier architecture using VPC, EC2, ALB, Auto Scaling, IAM, RDS, Route 53, and S3 with multi-AZ deployment achieving 99.99% uptime.",
                    "Configured secure networking with public/private subnets, security groups, routing tables, NAT Gateways, and IAM policies following cloud security best practices and least-privilege access.",
                    "Implemented scalable compute infrastructure with Application Load Balancer and Auto Scaling Groups to improve availability and fault tolerance during traffic spikes.",
                    "Integrated CloudWatch monitoring with custom metrics, alarms, and SNS notifications to observe infrastructure health and validate application availability post-deployment.",
                    "Built multi-region Azure infrastructure using Virtual Networks, VMs, Load Balancer, and Traffic Manager to implement high availability and traffic distribution across regions.",
                    "Configured Azure networking components (VNet peering, NSGs, Application Gateway) and validated regional failover behavior through Traffic Manager-based routing policies.",
                    "Strengthened practical understanding of cloud architecture, deployment strategies, and operational troubleshooting through end-to-end implementation of resilient cloud infrastructure."
                ]
            }
        ]
        
        for exp in experiences:
            # Title and company
            self.pdf.set_font("Helvetica", "B", 11)
            self.pdf.set_text_color(25, 55, 109)
            self.pdf.cell(0, 7, exp["title"], ln=True)
            
            self.pdf.set_font("Helvetica", "B", 10)
            self.pdf.set_text_color(60, 60, 60)
            self.pdf.cell(0, 6, exp["company"], ln=True)
            
            self.pdf.set_font("Helvetica", "I", 9)
            self.pdf.set_text_color(100, 100, 100)
            self.pdf.cell(0, 5, f"{exp['location']}  |  {exp['dates']}", ln=True)
            self.pdf.ln(1)
            
            # Bullets
            self.pdf.set_font("Helvetica", "", 9)
            self.pdf.set_text_color(50, 50, 50)
            for bullet in exp["bullets"]:
                self.pdf.set_x(15)
                # Handle long bullets with multi_cell
                self.pdf.multi_cell(185, 4.5, f"  - {bullet}")
                self.pdf.ln(0.5)
            self.pdf.ln(3)
    
    def _add_projects(self):
        """Add key projects with metrics"""
        self._section_title("KEY PROJECTS")
        
        projects = [
            {
                "name": "Multi-Cloud CI/CD Automation Platform",
                "tech": "AWS, Azure, Terraform, Jenkins, GitHub Actions, Argo CD, Helm, Kubernetes, Docker",
                "details": [
                    "Designed and implemented end-to-end CI/CD platform across AWS and Azure managing 50+ microservices",
                    "Integrated GitHub Actions for build/test, Terraform for infrastructure provisioning, Argo CD for GitOps deployments",
                    "Reduced deployment time from 45 min to 12 min (73% improvement) with 99.9% deployment success rate",
                    "Implemented automated rollback, canary deployments, and policy enforcement with Kyverno/OPA",
                    "Achieved zero-downtime deployments with blue-green strategy and automated health checks"
                ]
            },
            {
                "name": "Highly Available Three-Tier AWS Application Deployment",
                "tech": "AWS (VPC, EC2, ALB, ASG, RDS, Route 53, S3, CloudWatch, IAM, CloudFormation)",
                "details": [
                    "Architected HA three-tier web app with multi-AZ VPC, public/private subnets, NAT Gateways",
                    "Implemented ALB with target groups, Auto Scaling (3-50 instances), Multi-AZ RDS with read replicas",
                    "Configured Route 53 health checks, S3 static hosting with CloudFront CDN, SSL/TLS via ACM",
                    "Achieved 99.99% uptime with automated failover, CloudWatch monitoring, and SNS alerting"
                ]
            },
            {
                "name": "Azure Multi-Region Infrastructure with GitOps",
                "tech": "Azure (AKS, VNet, Load Balancer, Traffic Manager, Key Vault), Terraform, Flux v2, Helm",
                "details": [
                    "Built multi-region Azure infrastructure (East US, West Europe) with VNet peering and global Traffic Manager",
                    "Implemented Flux v2 GitOps with Kustomize overlays for 100+ microservices across environments",
                    "Configured Azure Key Vault for secrets, Azure Monitor for observability, Private Endpoints for security",
                    "Validated regional failover <30 seconds, achieving 40% cost savings vs single-region deployment"
                ]
            },
            {
                "name": "Observability Stack with GitOps (Prometheus/Grafana/Loki/Tempo/Datadog)",
                "tech": "Prometheus, Grafana, Loki, Tempo, Alertmanager, Datadog, Kubernetes, Helm, Argo CD",
                "details": [
                    "Deployed full observability stack via Helm/Argo CD: metrics, logs, traces unified in Grafana",
                    "Integrated Datadog APM for distributed tracing, correlated with logs/metrics reducing MTTR by 40%",
                    "Implemented 500+ custom dashboards, 200+ alerts with Alertmanager/PagerDuty routing",
                    "Process 50GB logs/day, 1M+ metrics/sec with 99.9% query availability"
                ]
            },
            {
                "name": "Serverless Event-Driven Architecture",
                "tech": "AWS Lambda, EventBridge, SQS, SNS, Step Functions, API Gateway, DynamoDB, CloudWatch",
                "details": [
                    "Built event-driven order processing pipeline handling 1M+ events/day with 99.9% reliability",
                    "Replaced EC2-based workers with Lambda + Step Functions reducing compute costs by 90%",
                    "Implemented dead-letter queues, retry policies, and X-Ray tracing for observability",
                    "Achieved sub-second latency with auto-scaling, zero operational overhead"
                ]
            }
        ]
        
        for proj in projects:
            self.pdf.set_font("Helvetica", "B", 10)
            self.pdf.set_text_color(25, 55, 109)
            self.pdf.cell(0, 6, proj["name"], ln=True)
            
            self.pdf.set_font("Helvetica", "I", 9)
            self.pdf.set_text_color(80, 80, 80)
            self.pdf.cell(0, 5, f"Tech Stack: {proj['tech']}", ln=True)
            
            self.pdf.set_font("Helvetica", "", 9)
            self.pdf.set_text_color(50, 50, 50)
            for detail in proj["details"]:
                self.pdf.set_x(15)
                self.pdf.multi_cell(185, 4.5, f"  - {detail}")
                self.pdf.ln(0.5)
            self.pdf.ln(3)
    
    def _add_education(self):
        """Add education"""
        self._section_title("EDUCATION")
        
        self.pdf.set_font("Helvetica", "B", 10)
        self.pdf.set_text_color(25, 55, 109)
        self.pdf.cell(0, 6, "Bachelor of Technology (Mechanical Engineering)", ln=True)
        
        self.pdf.set_font("Helvetica", "", 9)
        self.pdf.set_text_color(60, 60, 60)
        self.pdf.cell(0, 5, "Sree Vidyanikethan Engineering College  |  2019 - 2023", ln=True)
        self.pdf.ln(2)
    
    def _add_achievements(self):
        """Add achievements"""
        self._section_title("ACHIEVEMENTS & RECOGNITION")
        
        achievements = [
            "Received appreciation for consistent contribution, collaboration, and support during project deliverables at LTM",
            "Completed multiple end-to-end Cloud and DevOps implementation projects covering AWS, Azure, Kubernetes, Terraform, Jenkins, Docker, and CI/CD automation",
            "Successfully implemented GitOps workflows reducing deployment errors by 65% across 30+ microservices",
            "Established container security pipelines blocking 70%+ vulnerable images before production deployment",
            "Optimized cloud infrastructure costs by 25% using FinOps practices (Kubecost, Compute Optimizer)",
            "Active contributor to internal DevOps knowledge sharing sessions and documentation improvements"
        ]
        
        for ach in achievements:
            self.pdf.set_font("Helvetica", "", 9)
            self.pdf.set_text_color(50, 50, 50)
            self.pdf.set_x(15)
            self.pdf.multi_cell(185, 4.5, f"  - {ach}")
            self.pdf.ln(0.5)
    
    def _section_title(self, title: str):
        """Add a section title with styling"""
        self.pdf.ln(2)
        self.pdf.set_font("Helvetica", "B", 12)
        self.pdf.set_text_color(25, 55, 109)
        self.pdf.cell(0, 8, title, ln=True)
        
        # Underline
        self.pdf.set_draw_color(25, 55, 109)
        self.pdf.set_line_width(0.4)
        y = self.pdf.get_y()
        self.pdf.line(10, y, 200, y)
        self.pdf.ln(3)
    
    def _section_body(self, text: str):
        """Add section body text"""
        self.pdf.set_font("Helvetica", "", 9.5)
        self.pdf.set_text_color(50, 50, 50)
        self.pdf.multi_cell(0, 5, text)
        self.pdf.ln(2)


def build_optimized_resume(output_path: Path = Path("CV_Tarakananda_Optimized.pdf")) -> Path:
    """Main entry point to build the optimized resume"""
    builder = OptimizedResumeBuilder()
    return builder.build(output_path)


if __name__ == "__main__":
    output = build_optimized_resume()
    print(f"Optimized resume generated: {output}")