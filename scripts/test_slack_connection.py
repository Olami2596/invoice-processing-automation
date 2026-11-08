from src.notifications import send_slack_notification


if __name__ == "__main__":
    success = send_slack_notification(
        message=(
            "Invoice Processing Automation is connected to Slack!\n"
            "Slack notification delivery has been successfully tested."
        )
    )

    if success:
        print("Slack connection test successful.")
    else:
        print("Slack connection test failed. Check your configuration.")
