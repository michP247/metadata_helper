import gradio as gr
import modules.scripts as scripts
from modules.images import read_info_from_image
from modules.infotext_utils import parse_generation_parameters
from PIL import Image, UnidentifiedImageError
import modules.script_callbacks as script_callbacks
import re

try:
    from modules.ui_components import InputAccordion
except ImportError:
    InputAccordion = None

class Img2ImgMetadataHelperScript(scripts.Script):
    def __init__(self):
        super().__init__()
        self.is_target_instance = False
        # --- UI Element References ---
        self.prompt_input = None
        self.seed_input = None
        self.neg_prompt_input = None
        self.hidden_metadata_store = None
        self.display_extracted_prompt = None
        # --- Canvas Component Storage ---
        # We will store the canvas components we find here.
        self.canvas_background_components = []
        print("[Metadata Helper] Script instance initialized.")

    def title(self):
        return "Image Metadata Helper"

    def show(self, is_img2img):
        if is_img2img:
            self.is_target_instance = True
            return scripts.AlwaysVisible
        return False

    def on_canvas_image_change(self, pil_image: Image.Image):
        """Called when a canvas is updated. Receives a PIL Image directly."""
        print("\n--- [Metadata Helper] Canvas Image Change Detected ---")
        if not isinstance(pil_image, Image.Image):
            print("[Metadata Helper] Canvas cleared or invalid data. Resetting.")
            return {}, ""

        print(f"[Metadata Helper] Received PIL Image. Size: {pil_image.size}, Mode: {pil_image.mode}")
        try:
            geninfo, _ = read_info_from_image(pil_image)
            if geninfo is None:
                print("[Metadata Helper] No PNG metadata found in image.")
                return {}, ""
            params = parse_generation_parameters(geninfo)
            print(f"[Metadata Helper] Extracted metadata keys: {list(params.keys())}")
            extracted_prompt = params.get("Prompt", "")
            return params, extracted_prompt
        except Exception as e:
            print(f"[Metadata Helper] Error reading metadata: {e}")
            return {}, ""

    def _apply_modified_prompt(self, state_dict, remove_str, add_str):
        """Applies modifications to the extracted prompt."""
        if not isinstance(state_dict, dict) or not state_dict:
            gr.Warning("Metadata Helper: No metadata loaded. Upload an image first.")
            return ""
        
        original_prompt = state_dict.get("Prompt", "")
        modified_prompt = original_prompt

        if remove_str:
            words_to_remove = [word.strip() for word in remove_str.split(',') if word.strip()]
            for word in words_to_remove:
                escaped_word = re.escape(word)
                is_standard_word = word and word[0].isalnum() and word[-1].isalnum()
                pattern = r'\b' + escaped_word + r'\b' if is_standard_word else escaped_word
                # This regex logic handles commas and spacing around the word to remove.
                modified_prompt = re.sub(r'(,\s*|^)' + pattern + r'(\s*,|$)', r'\1\2', modified_prompt, flags=re.IGNORECASE)
            # Clean up leftover commas
            modified_prompt = re.sub(r'^,', '', re.sub(r',,', ',', modified_prompt.strip())).strip()

        if add_str:
            add_part = ", ".join([word.strip() for word in add_str.split(',') if word.strip()])
            if add_part:
                modified_prompt = f"{modified_prompt}, {add_part}" if modified_prompt else add_part
        
        return modified_prompt

    def after_component(self, component, **kwargs):
        """Finds UI elements and stores them for later processing in ui()."""
        if not self.is_target_instance:
            return

        elem_id = kwargs.get("elem_id")
        if elem_id == "img2img_prompt": self.prompt_input = component
        elif elem_id == "img2img_neg_prompt": self.neg_prompt_input = component
        elif elem_id == "img2img_seed": self.seed_input = component

        elem_classes = kwargs.get("elem_classes")
        if elem_classes and 'logical_image_background' in elem_classes and isinstance(component, gr.Textbox):
            # Store the found canvas component instead of binding immediately.
            self.canvas_background_components.append(component)
            print(f"[Metadata Helper] Found and stored canvas component: {kwargs.get('elem_id')}")

    def ui(self, is_img2img):
        """Creates the script's UI and binds events now that all components exist."""
        accordion_component = InputAccordion if InputAccordion else gr.Accordion
        # This list will be the return value of the function.
        all_created_components = []

        with accordion_component(label=self.title(), open=True) as acc:
            if InputAccordion:
                all_created_components.append(acc)

            self.hidden_metadata_store = gr.State({})
            
            with gr.Group():
                md = gr.Markdown("**Drag an image onto the main `img2img` canvas above to automatically load its metadata here.**")
                if not InputAccordion: all_created_components.append(md)

            with gr.Column():
                self.display_extracted_prompt = gr.Textbox(label="Extracted Prompt (read-only)", interactive=False, lines=3)
                prompt_remove_words = gr.Textbox(label="Remove words/phrases (comma-separated)")
                prompt_add_words = gr.Textbox(label="Add words/phrases to end (comma-separated)")
                if not InputAccordion: all_created_components.extend([self.display_extracted_prompt, prompt_remove_words, prompt_add_words])

            with gr.Row():
                send_seed_button = gr.Button("Apply Seed", variant="secondary")
                send_prompt_button = gr.Button("Apply Modified Prompt", variant="secondary")
                send_neg_prompt_button = gr.Button("Apply Neg Prompt", variant="secondary")
                if not InputAccordion: all_created_components.extend([send_seed_button, send_prompt_button, send_neg_prompt_button])

        # --- NOW BIND THE EVENTS ---
        # At this point, all our UI components (self.hidden_metadata_store, etc.)
        # and the canvas components (stored in the list) are guaranteed to exist.
        for canvas_comp in self.canvas_background_components:
            canvas_comp.change(
                fn=self.on_canvas_image_change,
                inputs=[canvas_comp],
                outputs=[self.hidden_metadata_store, self.display_extracted_prompt],
                queue=False
            )
        print(f"[Metadata Helper] Successfully bound change events for {len(self.canvas_background_components)} canvas components.")

        def get_value_from_state(key, state_dict, current_value, target_type=None):
            if not isinstance(state_dict, dict) or not state_dict:
                gr.Warning(f"Metadata Helper: No metadata loaded. Upload image first.")
                return current_value
            value = state_dict.get(key)
            if value is not None:
                if target_type == int:
                    try: return int(float(value))
                    except (ValueError, TypeError): return current_value
                return str(value).strip() if target_type == str else value
            return current_value

        send_seed_button.click(
            fn=lambda state, current: get_value_from_state("Seed", state, current, int),
            inputs=[self.hidden_metadata_store, self.seed_input], outputs=[self.seed_input], queue=False
        )
        send_prompt_button.click(
            fn=self._apply_modified_prompt,
            inputs=[self.hidden_metadata_store, prompt_remove_words, prompt_add_words],
            outputs=[self.prompt_input], queue=False
        )
        send_neg_prompt_button.click(
            fn=lambda state, current: get_value_from_state("Negative prompt", state, current, str),
            inputs=[self.hidden_metadata_store, self.neg_prompt_input],
            outputs=[self.neg_prompt_input], queue=False
        )
        
        return all_created_components

def on_app_started(demo, app):
    print("[Metadata Helper] Extension script loaded (Final Revised Version).")

script_callbacks.on_app_started(on_app_started)