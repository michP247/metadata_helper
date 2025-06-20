import gradio as gr
import modules.scripts as scripts
from modules.images import read_info_from_image
from modules.infotext_utils import parse_generation_parameters
from PIL import Image, UnidentifiedImageError
import modules.script_callbacks as script_callbacks
import re

class Img2ImgMetadataHelperScript(scripts.Script):
    def __init__(self):
        super().__init__()
        self.is_target_instance = False
        self.prompt_input = None
        self.seed_input = None
        self.neg_prompt_input = None
        self.hidden_metadata_store = None
        self.display_extracted_prompt = None
        self.canvas_background_components = []

    def title(self):
        return "Image Metadata Helper"

    def show(self, is_img2img):
        if is_img2img:
            self.is_target_instance = True
            return scripts.AlwaysVisible
        return False

    def _extract_metadata(self, pil_image: Image.Image):
        """Extracts metadata from a PIL Image, returning a dict and the raw prompt."""
        if not isinstance(pil_image, Image.Image):
            return {}, ""
        try:
            geninfo, _ = read_info_from_image(pil_image)
            if geninfo is None: return {}, ""
            params = parse_generation_parameters(geninfo)
            return params, params.get("Prompt", "")
        except Exception:
            return {}, ""

    def _modify_prompt(self, original_prompt, remove_str, add_str):
        """Applies string modifications to a prompt, correctly handling tags like LoRAs."""
        modified_prompt = original_prompt or ""
        if remove_str:
            words_to_remove = [word.strip() for word in remove_str.split(',') if word.strip()]
            for word in words_to_remove:
                escaped_word = re.escape(word)
                is_standard_word = word and word[0].isalnum() and word[-1].isalnum()
                pattern = r'\b' + escaped_word + r'\b' if is_standard_word else escaped_word
                # Multi-stage removal for robustness
                modified_prompt, n = re.subn(r',\s*' + pattern + r'\s*,', ',', modified_prompt, 1, flags=re.IGNORECASE)
                if n > 0: continue
                modified_prompt, n = re.subn(r'^\s*' + pattern + r'\s*,', '', modified_prompt, 1, flags=re.IGNORECASE)
                if n > 0: continue
                modified_prompt, n = re.subn(r',\s*' + pattern + r'\s*$', '', modified_prompt, 1, flags=re.IGNORECASE)
                if n > 0: continue
                modified_prompt, n = re.subn(r'\s+' + pattern + r'\s*$', '', modified_prompt, 1, flags=re.IGNORECASE)
                if n > 0: continue
                modified_prompt, n = re.subn(r'^\s*' + pattern + r'\s*$', '', modified_prompt, 1, flags=re.IGNORECASE)
            modified_prompt = modified_prompt.strip(' ,')
        if add_str:
            add_part = ", ".join([word.strip() for word in add_str.split(',') if word.strip()])
            if add_part:
                modified_prompt = f"{modified_prompt}, {add_part}" if modified_prompt and modified_prompt.strip() else add_part
        return modified_prompt.strip()

    def on_canvas_image_change(self, pil_image, auto_apply_prompt, auto_apply_seed, remove_str, add_str):
        """Main callback when a canvas image is uploaded."""
        metadata, extracted_prompt = self._extract_metadata(pil_image)
        
        # Initialize return values to "don't change"
        final_prompt = gr.update()
        final_seed = gr.update()

        if not metadata:
            return {}, "", final_prompt, final_seed

        if auto_apply_prompt:
            final_prompt = self._modify_prompt(extracted_prompt, remove_str, add_str)
        
        if auto_apply_seed:
            seed_val = metadata.get("Seed")
            if seed_val is not None:
                try:
                    final_seed = int(float(seed_val))
                except (ValueError, TypeError):
                    pass # Keep as gr.update() on failure

        return metadata, extracted_prompt, final_prompt, final_seed

    def after_component(self, component, **kwargs):
        """Finds and stores references to relevant UI components."""
        if not self.is_target_instance: return
        elem_id = kwargs.get("elem_id")
        if elem_id == "img2img_prompt": self.prompt_input = component
        elif elem_id == "img2img_neg_prompt": self.neg_prompt_input = component
        elif elem_id == "img2img_seed": self.seed_input = component
        elem_classes = kwargs.get("elem_classes")
        if elem_classes and 'logical_image_background' in elem_classes and isinstance(component, gr.Textbox):
            self.canvas_background_components.append(component)

    def ui(self, is_img2img):
        """Creates the script's UI and binds all events."""
        with gr.Accordion(label=self.title(), open=True):
            self.hidden_metadata_store = gr.State({})
            with gr.Group():
                gr.Markdown("**Drag an image onto the main `img2img` canvas to load its metadata.**")
            with gr.Column():
                with gr.Row():
                    auto_apply_prompt_checkbox = gr.Checkbox(label="Auto-apply prompt on upload", value=False)
                    auto_apply_seed_checkbox = gr.Checkbox(label="Include seed", value=False)
                self.display_extracted_prompt = gr.Textbox(label="Extracted Prompt (read-only)", interactive=False, lines=3)
                prompt_remove_words = gr.Textbox(label="Remove words/phrases (comma-separated)", placeholder="e.g., blurry, <lora:...>")
                prompt_add_words = gr.Textbox(label="Add words/phrases to end (comma-separated)", placeholder="e.g., 4k, masterpiece")
            with gr.Row():
                send_seed_button = gr.Button("Apply Seed", variant="secondary")
                send_prompt_button = gr.Button("Apply Modified Prompt", variant="secondary")
                send_neg_prompt_button = gr.Button("Apply Neg Prompt", variant="secondary")

        for canvas_comp in self.canvas_background_components:
            canvas_comp.change(
                fn=self.on_canvas_image_change,
                inputs=[canvas_comp, auto_apply_prompt_checkbox, auto_apply_seed_checkbox, prompt_remove_words, prompt_add_words],
                outputs=[self.hidden_metadata_store, self.display_extracted_prompt, self.prompt_input, self.seed_input],
                queue=False
            )

        def get_value_from_state(key, state_dict, current_value, target_type=None):
            if not isinstance(state_dict, dict) or not state_dict:
                gr.Warning("Metadata Helper: No metadata loaded. Upload image first.")
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
            fn=lambda state, remove, add: self._modify_prompt(state.get("Prompt",""), remove, add),
            inputs=[self.hidden_metadata_store, prompt_remove_words, prompt_add_words],
            outputs=[self.prompt_input], queue=False
        )
        send_neg_prompt_button.click(
            fn=lambda state, current: get_value_from_state("Negative prompt", state, current, str),
            inputs=[self.hidden_metadata_store, self.neg_prompt_input],
            outputs=[self.neg_prompt_input], queue=False
        )
        
        return [auto_apply_prompt_checkbox, auto_apply_seed_checkbox, self.display_extracted_prompt, prompt_remove_words, prompt_add_words, send_seed_button, send_prompt_button, send_neg_prompt_button]

script_callbacks.on_app_started(lambda d, a: None)