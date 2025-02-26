import os
import json
import requests
from typing import Dict, List, Optional
from datetime import datetime, timedelta
from collections import defaultdict
from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
import markdown

# Import your existing classes and modify them slightly for web integration
class ClickUpManager:
    def __init__(self, api_token: str):
        self.api_token = api_token
        self.headers = {
            "Authorization": api_token,
            "Content-Type": "application/json"
        }
        self.base_url = "https://api.clickup.com/api/v2"

    def get_all_teams(self) -> List[Dict]:
        """Get all teams (workspaces) the user has access to"""
        response = requests.get(
            f"{self.base_url}/team",
            headers=self.headers
        )
        response.raise_for_status()
        return response.json()["teams"]

    def get_spaces_in_team(self, team_id: str) -> List[Dict]:
        """Get all spaces within a specific team"""
        response = requests.get(
            f"{self.base_url}/team/{team_id}/space",
            headers=self.headers
        )
        response.raise_for_status()
        return response.json()["spaces"]

    def get_lists_in_space(self, space_id: str) -> List[Dict]:
        """Get all lists within a space"""
        url = f"{self.base_url}/space/{space_id}/list"
        response = requests.get(url, headers=self.headers)
        response.raise_for_status()
        return response.json()["lists"]

    def get_folder_lists(self, folder_id: str) -> List[Dict]:
        """Get all lists within a folder"""
        url = f"{self.base_url}/folder/{folder_id}/list"
        response = requests.get(url, headers=self.headers)
        response.raise_for_status()
        return response.json()["lists"]

    def get_folders_in_space(self, space_id: str) -> List[Dict]:
        """Get all folders within a space"""
        url = f"{self.base_url}/space/{space_id}/folder"
        response = requests.get(url, headers=self.headers)
        response.raise_for_status()
        return response.json()["folders"]

    def get_tasks_in_list(self, list_id: str, params: Optional[Dict] = None) -> List[Dict]:
        """Get all tasks within a list"""
        url = f"{self.base_url}/list/{list_id}/task"
        response = requests.get(url, headers=self.headers, params=params)
        response.raise_for_status()
        return response.json()["tasks"]

    def get_space_details(self, space_id: str) -> Dict:
        """Get space information"""
        response = requests.get(
            f"{self.base_url}/space/{space_id}",
            headers=self.headers
        )
        response.raise_for_status()
        return response.json()

class ClickUpTaskCounter(ClickUpManager):
    def count_tasks_in_space(self, space_id: str, days_back: Optional[int] = None) -> Dict:
        """
        Count tasks in a space with detailed breakdown

        Args:
            space_id (str): ID of the space to analyze
            days_back (int, optional): If provided, only count tasks from the last X days
        """
        # Initialize counters
        task_stats = {
            "total_tasks": 0,
            "completed_tasks": 0,
            "open_tasks": 0,
            "tasks_by_status": {},
            "tasks_by_priority": {
                "urgent": 0,
                "high": 0,
                "normal": 0,
                "low": 0,
                "no_priority": 0
            },
            "lists_count": 0,
            "folders_count": 0
        }

        # Set up date filtering if specified
        params = {}
        if days_back:
            start_date = datetime.now() - timedelta(days=days_back)
            params["date_created_gt"] = int(start_date.timestamp() * 1000)

        try:
            # Get folders in space
            folders = self.get_folders_in_space(space_id)
            task_stats["folders_count"] = len(folders)

            # Process folderless lists
            space_lists = self.get_lists_in_space(space_id)
            all_lists = space_lists.copy()

            # Process folders and their lists
            for folder in folders:
                folder_lists = self.get_folder_lists(folder["id"])
                all_lists.extend(folder_lists)

            task_stats["lists_count"] = len(all_lists)

            # Process all lists
            for list_item in all_lists:
                tasks = self.get_tasks_in_list(list_item["id"], params)

                for task in tasks:
                    task_stats["total_tasks"] += 1

                    # Count by status
                    status = task["status"]["status"]
                    task_stats["tasks_by_status"][status] = task_stats["tasks_by_status"].get(status, 0) + 1

                    if status.lower() in ["complete", "completed", "done"]:
                        task_stats["completed_tasks"] += 1
                    else:
                        task_stats["open_tasks"] += 1

                    # Count by priority
                    priority = task.get("priority")
                    if priority:
                        priority_name = priority["priority"].lower()
                        task_stats["tasks_by_priority"][priority_name] += 1
                    else:
                        task_stats["tasks_by_priority"]["no_priority"] += 1

            return task_stats
        except Exception as e:
            print(f"Error counting tasks: {e}")
            return task_stats

class SpaceAssigneeTracker(ClickUpManager):
    def get_space_assignees(self, space_id: str) -> Dict:
        """
        Get all assignees and their tasks in a specific space
        """
        # Initialize data structure for assignees
        assignee_data = defaultdict(lambda: {
            "name": "",
            "email": "",
            "username": "",
            "task_count": 0,
            "tasks": [],
            "lists": set()
        })

        try:
            # Get space details
            space = self.get_space_details(space_id)

            # Get all lists in the space
            lists = self.get_lists_in_space(space_id)

            for list_item in lists:
                tasks = self.get_tasks_in_list(list_item['id'])

                for task in tasks:
                    for assignee in task.get("assignees", []):
                        assignee_id = assignee["id"]

                        # Update assignee information
                        assignee_data[assignee_id].update({
                            "name": assignee.get("username", "No username"),
                            "email": assignee.get("email", "No email"),
                            "username": assignee.get("username", "No username")
                        })

                        # Update task information
                        assignee_data[assignee_id]["task_count"] += 1
                        assignee_data[assignee_id]["lists"].add(list_item["name"])

                        # Add task details
                        task_info = {
                            "task_id": task["id"],
                            "task_name": task["name"],
                            "status": task["status"]["status"],
                            "due_date": task.get("due_date", "No due date"),
                            "list_name": list_item["name"],
                            "priority": task.get("priority", {}).get("priority", "No priority")
                        }
                        assignee_data[assignee_id]["tasks"].append(task_info)

            # Convert sets to lists for JSON serialization
            for assignee_id in assignee_data:
                assignee_data[assignee_id]["lists"] = list(assignee_data[assignee_id]["lists"])

            return dict(assignee_data)
        except Exception as e:
            print(f"Error retrieving assignees: {e}")
            return {}

class ReportGenerator:
    def __init__(self, api_key=None):
        """Initialize with optional API key for GPT integration"""
        self.api_key = api_key
        if api_key:
            self.api_url = "https://api.groq.com/openai/v1/chat/completions"
            self.headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            }
        
    def _prepare_data_summary(self, data: Dict) -> Dict:
        """Prepare a summary of the data for the LLM"""
        summary = {
            "total_assignees": len(data),
            "total_tasks": sum(assignee["task_count"] for assignee in data.values()),
            "assignee_summaries": []
        }

        for assignee_id, assignee_data in data.items():
            # Calculate task status distribution
            status_count = {}
            for task in assignee_data["tasks"]:
                status = task["status"]
                status_count[status] = status_count.get(status, 0) + 1

            # Calculate priority distribution
            priority_count = {}
            for task in assignee_data["tasks"]:
                priority = task.get("priority", "No priority")
                priority_count[priority] = priority_count.get(priority, 0) + 1

            summary["assignee_summaries"].append({
                "name": assignee_data["name"],
                "email": assignee_data["email"],
                "task_count": assignee_data["task_count"],
                "lists": assignee_data["lists"],
                "status_distribution": status_count,
                "priority_distribution": priority_count
            })

        return summary

    def generate_report(self, assignee_data: Dict, task_stats: Dict, space_name: str) -> str:
        """Generate a report combining assignee data and task statistics"""
        if not self.api_key:
            # If no API key, generate a basic report
            return self._generate_basic_report(assignee_data, task_stats, space_name)
        
        # Prepare data summary for LLM
        summary = self._prepare_data_summary(assignee_data)
        
        # Create prompt for LLM
        prompt = f"""
        Please analyze this ClickUp workspace data and create a comprehensive report. 

        Workspace: {space_name}
        
        Task Statistics:
        Total Tasks: {task_stats['total_tasks']}
        Completed Tasks: {task_stats['completed_tasks']}
        Open Tasks: {task_stats['open_tasks']}
        Number of Lists: {task_stats['lists_count']}
        Number of Folders: {task_stats['folders_count']}
        
        Tasks by Status: {json.dumps(task_stats['tasks_by_status'])}
        Tasks by Priority: {json.dumps(task_stats['tasks_by_priority'])}
        
        Assignee Information:
        Total Assignees: {summary['total_assignees']}
        
        Detailed Assignee Information:
        {json.dumps(summary['assignee_summaries'], indent=2)}

        Please create a professional report that includes:
        1. Executive Summary
        2. Workload Distribution Analysis
        3. Task Status Overview
        4. Priority Distribution Analysis
        5. Team Member Performance Insights
        6. Recommendations for Workload Balancing
        7. Potential Bottlenecks or Areas of Concern

        Make the report data-driven but easy to understand. Include specific numbers and percentages where relevant.
        Format the report in Markdown.
        """

        try:
            # Generate report using GROQ
            payload = {
                "model": "mixtral-8x7b-32768",  # Using Mixtral model
                "messages": [
                    {"role": "system", "content": "You are a professional project management analyst creating a report based on ClickUp workspace data."},
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0.7,
                "max_tokens": 2000
            }

            response = requests.post(
                self.api_url,
                headers=self.headers,
                json=payload
            )

            response.raise_for_status()
            report = response.json()["choices"][0]["message"]["content"]
            return report

        except Exception as e:
            print(f"Error generating report with LLM: {str(e)}")
            # Fall back to basic report
            return self._generate_basic_report(assignee_data, task_stats, space_name)

    def _generate_basic_report(self, assignee_data: Dict, task_stats: Dict, space_name: str) -> str:
        """Generate a basic report without using LLM"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        report = f"""# ClickUp Workspace Analysis Report
        
## Workspace: {space_name}
Generated on: {timestamp}

## Executive Summary
This report provides an analysis of your ClickUp workspace "{space_name}".

## Task Statistics
- **Total Tasks**: {task_stats['total_tasks']}
- **Completed Tasks**: {task_stats['completed_tasks']} ({task_stats['completed_tasks']/task_stats['total_tasks']*100:.1f}% if tasks exist else 0)
- **Open Tasks**: {task_stats['open_tasks']}
- **Number of Lists**: {task_stats['lists_count']}
- **Number of Folders**: {task_stats['folders_count']}

## Task Status Distribution
"""
        
        for status, count in task_stats['tasks_by_status'].items():
            percentage = (count / task_stats['total_tasks'] * 100) if task_stats['total_tasks'] > 0 else 0
            report += f"- **{status}**: {count} ({percentage:.1f}%)\n"
            
        report += """
## Task Priority Distribution
"""
        
        for priority, count in task_stats['tasks_by_priority'].items():
            percentage = (count / task_stats['total_tasks'] * 100) if task_stats['total_tasks'] > 0 else 0
            report += f"- **{priority.capitalize()}**: {count} ({percentage:.1f}%)\n"
            
        report += """
## Assignee Workload
"""
        
        for assignee_id, data in assignee_data.items():
            report += f"""
### {data['name']}
- **Email**: {data['email']}
- **Total Tasks**: {data['task_count']}
- **Active in Lists**: {', '.join(data['lists'][:5])}{"..." if len(data['lists']) > 5 else ""}
"""
            
        report += """
## Recommendations
1. Review workload distribution among team members to ensure balanced assignments
2. Address any tasks with high priority that remain unresolved
3. Consider consolidating or archiving unused lists to streamline workspace


"""
        
        return report


# class ClickUpReportGenerator:
#     def __init__(self, groq_api_key: Optional[str] = None):
#         """
#         Initialize with Groq API key for enhanced report generation.
        
#         Args:
#             groq_api_key: API key for Groq. If None, falls back to basic report.
#         """
#         self.api_key = groq_api_key
#         if groq_api_key:
#             self.api_url = "https://api.groq.com/openai/v1/chat/completions"
#             self.headers = {
#                 "Authorization": f"Bearer {groq_api_key}",
#                 "Content-Type": "application/json"
#             }
    
#     def _prepare_data_summary(self, assignee_data: Dict) -> Dict:
#         """
#         Prepare a summary of assignee data for LLM analysis.
        
#         Args:
#             assignee_data: Dictionary containing data about assignees and their tasks
            
#         Returns:
#             Dictionary with summarized data for LLM consumption
#         """
#         summary = {
#             "total_assignees": len(assignee_data),
#             "total_tasks": sum(assignee["task_count"] for assignee in assignee_data.values()),
#             "assignee_summaries": []
#         }

#         for assignee_id, assignee_data in assignee_data.items():
#             # Calculate task status distribution
#             status_count = {}
#             for task in assignee_data["tasks"]:
#                 status = task["status"]
#                 status_count[status] = status_count.get(status, 0) + 1

#             # Calculate priority distribution
#             priority_count = {}
#             for task in assignee_data["tasks"]:
#                 priority = task.get("priority", "No priority")
#                 priority_count[priority] = priority_count.get(priority, 0) + 1
                
#             # Calculate time metrics if available
#             time_metrics = {}
#             overdue_tasks = 0
#             upcoming_tasks = 0
            
#             for task in assignee_data["tasks"]:
#                 if task.get("due_date") and task.get("status") != "complete":
#                     due_date = datetime.fromtimestamp(int(task["due_date"])/1000)
#                     now = datetime.now()
#                     if due_date < now:
#                         overdue_tasks += 1
#                     elif (due_date - now).days <= 7:
#                         upcoming_tasks += 1
            
#             time_metrics["overdue_tasks"] = overdue_tasks
#             time_metrics["upcoming_tasks"] = upcoming_tasks

#             # Create assignee summary
#             assignee_summary = {
#                 "name": assignee_data["name"],
#                 "email": assignee_data["email"],
#                 "task_count": assignee_data["task_count"],
#                 "lists": assignee_data["lists"],
#                 "status_distribution": status_count,
#                 "priority_distribution": priority_count,
#                 "time_metrics": time_metrics
#             }
            
#             summary["assignee_summaries"].append(assignee_summary)

#         return summary
    
#     def _analyze_team_patterns(self, assignee_summaries: List[Dict]) -> Dict:
#         """
#         Extract team-wide patterns from assignee summaries.
        
#         Args:
#             assignee_summaries: List of dictionaries with assignee data
            
#         Returns:
#             Dictionary with team-wide patterns and insights
#         """
#         patterns = {
#             "workload_distribution": {},
#             "status_distribution": {},
#             "priority_handling": {},
#             "potential_bottlenecks": []
#         }
        
#         # Analyze workload distribution
#         task_counts = [summary["task_count"] for summary in assignee_summaries]
#         if task_counts:
#             patterns["workload_distribution"] = {
#                 "max_tasks": max(task_counts),
#                 "min_tasks": min(task_counts),
#                 "avg_tasks": sum(task_counts) / len(task_counts)
#             }
            
#             # Identify potential workload imbalances
#             for summary in assignee_summaries:
#                 if summary["task_count"] > patterns["workload_distribution"]["avg_tasks"] * 1.5:
#                     patterns["potential_bottlenecks"].append(f"High workload for {summary['name']}")
        
#         # Aggregate status distribution
#         all_statuses = {}
#         for summary in assignee_summaries:
#             for status, count in summary["status_distribution"].items():
#                 all_statuses[status] = all_statuses.get(status, 0) + count
        
#         patterns["status_distribution"] = all_statuses
        
#         return patterns

#     def generate_report(self, assignee_data: Dict, task_stats: Dict, space_name: str) -> Tuple[str, Optional[str]]:
#         """
#         Generate a comprehensive report using Groq LLM if available.
        
#         Args:
#             assignee_data: Dictionary containing data about assignees and their tasks
#             task_stats: Dictionary containing overall task statistics
#             space_name: Name of the ClickUp workspace
            
#         Returns:
#             Tuple containing the report content and optionally a file path if saved
#         """
#         timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
#         report_filename = f"clickup_analysis_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
        
#         if not self.api_key:
#             # If no API key, generate a basic report
#             report = self._generate_basic_report(assignee_data, task_stats, space_name, timestamp)
            
#             # Save report
#             with open(report_filename, 'w') as f:
#                 f.write(report)
                
#             return report, report_filename
        
#         try:
#             # Prepare data for LLM
#             summary = self._prepare_data_summary(assignee_data)
#             patterns = self._analyze_team_patterns(summary["assignee_summaries"])
            
#             # Create enhanced prompt for LLM
#             prompt = f"""
#             Please analyze this ClickUp workspace data and create a comprehensive report with deep insights. 

#             Workspace: {space_name}
#             Report Date: {timestamp}
            
#             TASK STATISTICS:
#             Total Tasks: {task_stats['total_tasks']}
#             Completed Tasks: {task_stats['completed_tasks']} ({(task_stats['completed_tasks']/task_stats['total_tasks']*100 if task_stats['total_tasks'] > 0 else 0):.1f}%)
#             Open Tasks: {task_stats['open_tasks']}
#             Number of Lists: {task_stats['lists_count']}
#             Number of Folders: {task_stats['folders_count']}
            
#             Tasks by Status: {json.dumps(task_stats['tasks_by_status'])}
#             Tasks by Priority: {json.dumps(task_stats['tasks_by_priority'])}
            
#             TEAM ANALYSIS:
#             Total Assignees: {summary['total_assignees']}
#             Workload Distribution: {json.dumps(patterns['workload_distribution'])}
#             Potential Bottlenecks: {json.dumps(patterns['potential_bottlenecks'])}
            
#             DETAILED ASSIGNEE INFORMATION:
#             {json.dumps(summary['assignee_summaries'], indent=2)}

#             Please create a professional report that includes:
#             1. Executive Summary with key metrics and findings
#             2. Workload Distribution Analysis with attention to balance and capacity
#             3. Task Status Analysis with focus on progress and blockers
#             4. Priority Analysis highlighting attention to critical work
#             5. Team Member Performance Insights identifying strengths and areas for support
#             6. Tactical Recommendations for workload balancing and process improvement
#             7. Strategic Insights on team performance patterns
            
#             Make the report data-driven with specific metrics, percentages, and comparisons.
#             Include visualization suggestions where appropriate.
#             Format the report in Markdown with clear headings, bullet points, and emphasis on key findings.
#             """

#             # Generate report using Groq
#             payload = {
#                 "model": "mixtral-8x7b-32768",  # Using Mixtral model
#                 "messages": [
#                     {"role": "system", "content": "You are a professional project management analyst with expertise in team productivity, workload balancing, and ClickUp. Create a detailed, insightful report that goes beyond surface metrics to provide actionable intelligence."},
#                     {"role": "user", "content": prompt}
#                 ],
#                 "temperature": 0.5,  # Lower temperature for more focused analysis
#                 "max_tokens": 3000   # More tokens for comprehensive analysis
#             }

#             response = requests.post(
#                 self.api_url,
#                 headers=self.headers,
#                 json=payload
#             )

#             response.raise_for_status()
#             report = response.json()["choices"][0]["message"]["content"]
            
#             # Save the report
#             with open(report_filename, 'w') as f:
#                 f.write(report)
                
#             return report, report_filename

#         except Exception as e:
#             print(f"Error generating report with LLM: {str(e)}")
#             # Fall back to basic report
#             report = self._generate_basic_report(assignee_data, task_stats, space_name, timestamp)
            
#             # Save report
#             with open(report_filename, 'w') as f:
#                 f.write(report)
                
#             return report, report_filename

#     def _generate_basic_report(self, assignee_data: Dict, task_stats: Dict, space_name: str, timestamp: str) -> str:
#         """
#         Generate a basic report without using LLM.
        
#         Args:
#             assignee_data: Dictionary containing data about assignees and their tasks
#             task_stats: Dictionary containing overall task statistics
#             space_name: Name of the ClickUp workspace
#             timestamp: Time string for report generation
            
#         Returns:
#             String containing the report content
#         """
#         report = f"""# ClickUp Workspace Analysis Report
        
# ## Workspace: {space_name}
# Generated on: {timestamp}

# ## Executive Summary
# This report provides an analysis of your ClickUp workspace "{space_name}" with {task_stats['total_tasks']} tasks across {task_stats['lists_count']} lists.

# ## Task Statistics
# - **Total Tasks**: {task_stats['total_tasks']}
# - **Completed Tasks**: {task_stats['completed_tasks']} ({(task_stats['completed_tasks']/task_stats['total_tasks']*100 if task_stats['total_tasks'] > 0 else 0):.1f}%)
# - **Open Tasks**: {task_stats['open_tasks']}
# - **Number of Lists**: {task_stats['lists_count']}
# - **Number of Folders**: {task_stats['folders_count']}

# ## Task Status Distribution
# """
        
#         for status, count in task_stats['tasks_by_status'].items():
#             percentage = (count / task_stats['total_tasks'] * 100) if task_stats['total_tasks'] > 0 else 0
#             report += f"- **{status}**: {count} ({percentage:.1f}%)\n"
            
#         report += """
# ## Task Priority Distribution
# """
        
#         for priority, count in task_stats['tasks_by_priority'].items():
#             percentage = (count / task_stats['total_tasks'] * 100) if task_stats['total_tasks'] > 0 else 0
#             report += f"- **{priority if priority else 'No priority'}**: {count} ({percentage:.1f}%)\n"
            
#         report += """
# ## Assignee Workload
# """
        
#         # Calculate average tasks per assignee for comparison
#         total_assignees = len(assignee_data)
#         avg_tasks = task_stats['total_tasks'] / total_assignees if total_assignees > 0 else 0
        
#         for assignee_id, data in assignee_data.items():
#             # Calculate completed vs open tasks
#             completed = 0
#             for task in data['tasks']:
#                 if task["status"].lower() in ["complete", "completed", "done"]:
#                     completed += 1
            
#             completion_rate = (completed / data['task_count'] * 100) if data['task_count'] > 0 else 0
            
#             # Compare to average
#             workload_comparison = data['task_count'] / avg_tasks if avg_tasks > 0 else 1
#             workload_status = "Average"
#             if workload_comparison > 1.2:
#                 workload_status = "Above Average"
#             elif workload_comparison < 0.8:
#                 workload_status = "Below Average"
            
#             report += f"""
# ### {data['name']}
# - **Email**: {data['email']}
# - **Total Tasks**: {data['task_count']} ({workload_status} workload)
# - **Completion Rate**: {completion_rate:.1f}%
# - **Active in Lists**: {', '.join(data['lists'][:5])}{"..." if len(data['lists']) > 5 else ""}
# """
            
#         report += """
# ## Recommendations
# 1. Review workload distribution among team members to ensure balanced assignments
# 2. Address any tasks with high priority that remain unresolved
# 3. Consider consolidating or archiving unused lists to streamline workspace
# 4. Set up regular review sessions to maintain progress on open tasks
# 5. Evaluate completion rates across team members to identify areas for coaching
# """
        
#         return report


app = Flask(__name__)
app.secret_key = os.urandom(24)
app.config['UPLOAD_FOLDER'] = 'reports'
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Routes
@app.route('/')
def index():
    api_token = session.get('api_token')
    if not api_token:
        return render_template('login.html')
    
    return redirect(url_for('workspaces'))

@app.route('/login', methods=['POST'])
def login():
    api_token = request.form.get('api_token')
    
    if not api_token:
        flash('API token is required', 'danger')
        return redirect(url_for('index'))
    
    # Verify API token works
    try:
        manager = ClickUpManager(api_token)
        manager.get_all_teams()
        session['api_token'] = api_token
        flash('Successfully logged in', 'success')
        return redirect(url_for('workspaces'))
    except Exception as e:
        flash(f'Invalid API token: {str(e)}', 'danger')
        return redirect(url_for('index'))

@app.route('/logout')
def logout():
    session.pop('api_token', None)
    flash('Logged out successfully', 'success')
    return redirect(url_for('index'))

@app.route('/workspaces')
def workspaces():
    api_token = session.get('api_token')
    if not api_token:
        flash('Please log in first', 'warning')
        return redirect(url_for('index'))
    
    try:
        manager = ClickUpManager(api_token)
        teams = manager.get_all_teams()
        return render_template('workspaces.html', teams=teams)
    except Exception as e:
        flash(f'Error retrieving workspaces: {str(e)}', 'danger')
        return redirect(url_for('index'))

@app.route('/spaces/<team_id>')
def spaces(team_id):
    api_token = session.get('api_token')
    if not api_token:
        flash('Please log in first', 'warning')
        return redirect(url_for('index'))
    
    try:
        manager = ClickUpManager(api_token)
        spaces = manager.get_spaces_in_team(team_id)
        return render_template('spaces.html', spaces=spaces, team_id=team_id)
    except Exception as e:
        flash(f'Error retrieving spaces: {str(e)}', 'danger')
        return redirect(url_for('workspaces'))

@app.route('/space/<space_id>')
def space_dashboard(space_id):
    api_token = session.get('api_token')
    if not api_token:
        flash('Please log in first', 'warning')
        return redirect(url_for('index'))
    
    days_back = request.args.get('days_back', default=30, type=int)
    
    try:
        manager = ClickUpManager(api_token)
        space_details = manager.get_space_details(space_id)
        
        # Get task statistics
        task_counter = ClickUpTaskCounter(api_token)
        task_stats = task_counter.count_tasks_in_space(space_id, days_back=days_back)
        
        # Get assignee data
        assignee_tracker = SpaceAssigneeTracker(api_token)
        assignee_data = assignee_tracker.get_space_assignees(space_id)
        
        return render_template(
            'space_dashboard.html', 
            space=space_details, 
            task_stats=task_stats,
            assignee_data=assignee_data,
            days_back=days_back
        )
    except Exception as e:
        flash(f'Error retrieving space data: {str(e)}', 'danger')
        return redirect(url_for('workspaces'))

@app.route('/generate_report/<space_id>', methods=['POST'])
def generate_report(space_id):
    api_token = session.get('api_token')
    if not api_token:
        flash('Please log in first', 'warning')
        return redirect(url_for('index'))
    
    groq_api_key = request.form.get('groq_api_key', '')
    
    try:
        # Get space details first
        manager = ClickUpManager(api_token)
        space_details = manager.get_space_details(space_id)
        space_name = space_details.get('name', 'Unknown Space')
        
        # Get task statistics
        task_counter = ClickUpTaskCounter(api_token)
        task_stats = task_counter.count_tasks_in_space(space_id)
        
        # Get assignee data
        assignee_tracker = SpaceAssigneeTracker(api_token)
        assignee_data = assignee_tracker.get_space_assignees(space_id)
        
        # Generate report
        report_generator = ReportGenerator(groq_api_key if groq_api_key else None)
        report_content = report_generator.generate_report(assignee_data, task_stats, space_name)
        
        # Save report to file
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"clickup_report_{space_id}_{timestamp}.md"
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        
        with open(filepath, 'w') as f:
            f.write(report_content)
        
        # Store report in session for display
        session['report_content'] = report_content
        session['report_filename'] = filename
        
        flash('Report generated successfully', 'success')
        return redirect(url_for('view_report'))
    except Exception as e:
        flash(f'Error generating report: {str(e)}', 'danger')
        return redirect(url_for('space_dashboard', space_id=space_id))

# @app.route('/view_report')
# def view_report():
#     api_token = session.get('api_token')
#     if not api_token:
#         flash('Please log in first', 'warning')
#         return redirect(url_for('index'))
    
#     report_content = session.get('report_content')
#     if not report_content:
#         flash('No report found', 'warning')
#         return redirect(url_for('workspaces'))
    
#     filename = session.get('report_filename', 'report.md')
#     return render_template('view_report.html', report_content=report_content, filename=filename)

# Add to your imports
import markdown

@app.route('/view_report')
def view_report():
    api_token = session.get('api_token')
    if not api_token:
        flash('Please log in first', 'warning')
        return redirect(url_for('index'))
    
    report_content = session.get('report_content')
    if not report_content:
        flash('No report found', 'warning')
        return redirect(url_for('workspaces'))
    
    # Convert markdown to HTML
    html_content = markdown.markdown(report_content)
    
    filename = session.get('report_filename', 'report.md')
    return render_template('view_report.html', report_content=html_content, filename=filename)

@app.route('/download_report/<filename>')
def download_report(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

# API routes for AJAX calls
@app.route('/api/task_stats/<space_id>')
def api_task_stats(space_id):
    api_token = session.get('api_token')
    if not api_token:
        return jsonify({'error': 'Unauthorized'}), 401
    
    days_back = request.args.get('days_back', default=30, type=int)
    
    try:
        # Get task statistics
        task_counter = ClickUpTaskCounter(api_token)
        task_stats = task_counter.count_tasks_in_space(space_id, days_back=days_back)
        return jsonify(task_stats)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# Main function to run the app
if __name__ == '__main__':
    app.run(debug=True)