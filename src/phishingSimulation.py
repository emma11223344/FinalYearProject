LEGITIMATE_SCENARIOS = {
    "Team Lunch Invite",
    "IT Maintenance Notice",
    "Quarterly Town Hall",
    "Training Reminder",
    "Security Patch Advisory",
    "Facilities Access Notice",
    "Project Kickoff Invite",
    "Payroll Schedule Update",
}


def annotate_action_status_for_admin(interaction):
    scenario = interaction.campaign or ""
    is_legitimate = scenario in LEGITIMATE_SCENARIOS
    is_reported = interaction.action == "Reported"

    interaction.simulation_type_label = "Not Phishing" if is_legitimate else "Phishing"
    interaction.status_label = "Reported" if is_reported else "Unreported"
    interaction.is_correct = (not is_legitimate) if is_reported else is_legitimate
    interaction.status_class = "status-correct" if interaction.is_correct else "status-incorrect"

    if is_legitimate:
        interaction.awareness_score = None
        interaction.awareness_score_label = "N/A"
    elif interaction.action in ("Reported", "Ignored"):
        interaction.awareness_score = 100
        interaction.awareness_score_label = "100%"
    elif interaction.action == "Clicked Link":
        interaction.awareness_score = 50
        interaction.awareness_score_label = "50%"
    elif interaction.action == "Completed Legitimate Form":
        interaction.awareness_score = 0
        interaction.awareness_score_label = "0%"
    else:
        interaction.awareness_score = None
        interaction.awareness_score_label = "N/A"


def simulation_requires_sensitive_input(simulation):
    return simulation.get("display_link") != simulation.get("link") or bool(simulation.get("red_flags"))
