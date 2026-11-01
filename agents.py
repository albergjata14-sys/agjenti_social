import os

class MasterCEO:
    def __init__(self):
        self.name = "Master CEO"
        self.description = "Koordinatori kryesor."

    def coordinate_task(self, task_description, uploaded_image=None):
        response = f"[{self.name}]: Kam marrë kërkesën tuaj. Po koordinoj burimet..."
        insta_agent = InstagramAgent()
        result = insta_agent.generate_content(task_description, uploaded_image)
        return response + "\n\n" + result

class InstagramAgent:
    def __init__(self):
        self.name = "Instagram Agent"

    def generate_content(self, task_description, uploaded_image=None):
        status = "Me foto të ngarkuar." if uploaded_image else "Pa foto."
        caption = "Përshëndetje miq! Sigurojini ambientet tuaja me sistemet më të reja nga Smart Albania. Na shkruani për një konsultë! #SmartAlbania #Siguri"
        reel = "🎬 Skenari Reel: 1. Pamje e pajisjes. 2. Shpjegim i qetësisë. 3. Na kontaktoni."
        return f"[{self.name}] Analiza u krye! ({status})\n\nCaption:\n{caption}\n\n{reel}"
