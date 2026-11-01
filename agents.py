import os

class MasterCEO:
    def __init__(self):
        self.name = "Master CEO"
        self.description = "Koordinatori kryesor, ekspert i kodimit dhe zhvillimit të sistemeve."
        # Këtu mund të vendosësh çelësin e API-së nëse dëshiron lidhje direkte me Claude ose Gemini
        self.system_instructions = (
            "Ti je Master CEO, një agjent kryesor i inteligjencës artificiale për SmartAlbania. "
            "Ke njohuri të thella në programim (Python, Streamlit, HTML/CSS, Git), zhvillim sistemesh, "
            "dhe automatizim. Jep gjithmonë përgjigje të sakta, kode të plota kur të kërkohen, "
            "dhe udhëzo përdoruesin hap pas hapi si një inxhinier i vërtetë software."
        )

    def coordinate_task(self, task_description, uploaded_image=None):
        # Këtu mund të integrozësh thirrjen reale të API-së (Claude/Gemini)
        # Për momentin, ndërtojmë logjikën që përgjigjet si ekspert kodimi:
        
        prompt_lower = task_description.lower()
        
        if "kod" or "krijo" or "ndrysho" or "faqe" in prompt_lower:
            return (
                f"[{self.name}]: E kuptova plotësisht kërkesën tuaj. "
                f"Si ekspert teknik, po ju përgatis zgjidhjen e plotë për: '{task_description}'. "
                f"Më poshtë keni strukturën e kodit që ju duhet ta zëvendësoni te projekti juaj në Spck Editor, "
                f"e cila përfshin funksionalitetin e kërkuar në kohë reale."
            )
        else:
            return (
                f"[{self.name}]: Përshëndetje! E mora mesazhin tuaj: '{task_description}'. "
                f"Si CEO Master, po koordinoj sistemin e agjentëve të SmartAlbania që të zbatojmë këtë kërkesë "
                f"menjëherë. Si dëshironi të procedojmë më tej me kodimin?"
            )

class InstagramAgent:
    def __init__(self):
        self.name = "Instagram Agent"

    def generate_content(self, task_description, uploaded_image=None):
        return f"Instagram Agent: Analizova kërkesën për Instagram lidhur me: '{task_description}'. Gati për postim dhe gjenerim captions!"
