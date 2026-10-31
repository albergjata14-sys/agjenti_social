import os

class MasterCEO:
    def __init__(self):
        self.agents = {
            "whatsapp": "Gati për menaxhimin e mesazheve dhe klientëve.",
            "instagram": "Gati për analizë fotosh, captions, reels dhe orare postimi.",
            "facebook": "Gati për postime dhe menaxhim faqeje.",
            "tiktok": "Gati për video të shkurtra dhe tendenca.",
            "web": "Gati për përditësime dhe menaxhim faqjeje uebi.",
            "preventiva": "Gati për llogaritjen dhe dërgimin e preventivave automatike."
        }
        self.tasks_queue = []

    def assign_task(self, agent_name, task_description):
        if agent_name in self.agents:
            task = {"agent": agent_name, "task": task_description, "status": "Pending Approval"}
            self.tasks_queue.append(task)
            return f"Detyra iu caktua agjentit '{agent_name}' dhe po pret konfirmimin tënd."
        return "Agjenti nuk ekziston."

class InstagramAgent:
    def __init__(self):
        self.name = "Instagram Agent"

    def process_image_and_prepare_post(self, image_path, user_prompt):
        # Këtu do të lidhet Gemini për të gjeneruar përmbajtjen për SmartAlbania
        caption = f"Instalim profesionist nga SmartAlbania! {user_prompt} - Na kontaktoni për kamerat dhe sistemet smart."
        hashtags = "#SmartAlbania #Tirana #SecuritySystems #SmartHome #KameraSigurie"
        
        return {
            "status": "Gati për Aprovim",
            "caption_suggestion": f"{caption}\n\n{hashtags}",
            "best_posting_time": "Sot në orën 18:30 (Bazuar në aktivitetin e audiencës)"
        }
