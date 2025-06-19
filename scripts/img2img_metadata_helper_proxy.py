
import gradio as gr
import modules.scripts as scripts
from modules.images import read_info_from_image
from modules.infotext_utils import parse_generation_parameters
from PIL import Image, UnidentifiedImageError
import json
import os
import base64
from io import BytesIO
import modules.script_callbacks as script_callbacks
from fastapi import FastAPI
import re # Import regular expressions module

# Use InputAccordion conditionally
try:
    from modules.ui_components import InputAccordion
except ImportError:
    InputAccordion = None # Fallback for older versions


class Img2ImgMetadataHelperScript(scripts.Script):

    def __init__(self):
        super().__init__()
        self.prompt_input = None
        self.seed_input = None
        self.neg_prompt_input = None

        # Component to store the extracted metadata dictionary
        self.hidden_metadata_store = None
        # Reference to our proxy image component
        self.proxy_image_input = None
        # Reference to the textbox displaying the extracted prompt
        self.display_extracted_prompt = None
        print("[Metadata Helper] Script instance initialized")

    def title(self):
        return "Image Metadata Helper"

    def show(self, is_img2img):
        return scripts.AlwaysVisible if is_img2img else False

    def _extract_metadata_from_pil(self, image_obj: Image.Image):
        """Extracts metadata directly from a PIL Image."""
        if image_obj is None:
            return {}, "No image provided"
        try:
            geninfo, _ = read_info_from_image(image_obj)
            if geninfo is None:
                return {}, "No metadata found in image"
            params = parse_generation_parameters(geninfo)
            return params, None
        except UnidentifiedImageError:
            return {}, "Could not read image format"
        except Exception as e:
            print(f"[Metadata Helper] Error reading metadata from PIL: {e}")
            return {}, f"Error reading metadata: {e}"

    def on_proxy_image_change(self, image_input):
        """
        Called when the proxy image component changes.
        Extracts metadata, returns it for hidden store AND extracts prompt for display.
        """
        print(f"[Metadata Helper] on_proxy_image_change triggered. Input type: {type(image_input)}")
        extracted_prompt_display = "" # Default empty display prompt
        metadata = {} # Default empty metadata

        if image_input is None: # Handle image clearing
            print("[Metadata Helper] Proxy image cleared.")
            # Return empty dict for state, empty string for display
            return {}, ""

        pil_image = None
        if isinstance(image_input, Image.Image):
            pil_image = image_input
            print("[Metadata Helper] Input is a PIL image.")
        else:
             print(f"[Metadata Helper Warning] Expected PIL Image from proxy, got {type(image_input)}")
             return {}, "" # Return empty if unexpected type


        if pil_image:
            metadata, error = self._extract_metadata_from_pil(pil_image)
            if error and error not in ["No metadata found in image", "No image provided"]:
                 gr.Warning(f"Metadata Helper: {error}")
            elif not metadata and error != "No image provided":
                 print("[Metadata Helper] No metadata found in uploaded proxy image.")
            elif metadata:
                 print(f"[Metadata Helper] Storing metadata from proxy: {list(metadata.keys())}")
                 # Extract prompt specifically for the display textbox
                 extracted_prompt_display = metadata.get("Prompt", "")
                 print(f"[Metadata Helper] Extracted prompt for display: '{extracted_prompt_display[:100]}...'")

            # Return both the full metadata dict and the extracted prompt string
            return metadata, extracted_prompt_display
        else:
            print("[Metadata Helper] No valid PIL image found in proxy input.")
            return {}, ""

    def _apply_modified_prompt(self, state_dict, remove_str, add_str):
        """Applies removals and additions to the prompt stored in state."""
        print(f"[Metadata Helper] Applying prompt modification.")
        print(f"  - Remove: '{remove_str}'")
        print(f"  - Add: '{add_str}'")

        if not isinstance(state_dict, dict) or not state_dict:
            gr.Warning("Metadata Helper: No metadata loaded. Upload image first.")
            return "" # Return empty string if no state

        original_prompt = state_dict.get("Prompt", None)

        if original_prompt is None:
            gr.Warning("Metadata Helper: 'Prompt' not found in stored metadata.")
            return "" # Return empty string if no prompt found

        modified_prompt = original_prompt
        print(f"  - Original Prompt: '{modified_prompt[:100]}...'")

        # --- Removal ---
        if remove_str:
            words_to_remove = [word.strip() for word in remove_str.split(',') if word.strip()]
            if words_to_remove:
                print(f"  - Removing words: {words_to_remove}")
                for word in words_to_remove:
                    # Escape any special regex characters in the user's input
                    escaped_word = re.escape(word)

                    # Conditionally apply word boundaries (\b).
                    # A "standard word" starts and ends with a letter, number, or underscore.
                    # Tags like "<lora...>" or "(masterpiece)" do not, and should not use \b.
                    is_standard_word = word and re.match(r'\w', word[0]) and re.match(r'\w', word[-1])

                    if is_standard_word:
                        # For standard words like "shirt", use word boundaries to avoid matching "t-shirt".
                        pattern = r'\b' + escaped_word + r'\b'
                        print(f"  - Using standard word pattern for '{word}': {pattern}")
                    else:
                        # For tags like "<lora...>", match the exact escaped string.
                        pattern = escaped_word
                        print(f"  - Using tag/phrase pattern for '{word}': {pattern}")

                    # Case 1: , word, -> , (handles items in the middle of a list)
                    pattern_comma_both = r',\s*' + pattern + r'\s*,'
                    modified_prompt = re.sub(pattern_comma_both, ', ', modified_prompt, flags=re.IGNORECASE)
                    # Case 2: word, -> (handles item at the start)
                    pattern_comma_after = r'(^|\s)' + pattern + r'\s*,'
                    modified_prompt = re.sub(pattern_comma_after, r'\1', modified_prompt, flags=re.IGNORECASE)
                     # Case 3: , word -> (handles item at the end)
                    pattern_comma_before = r',\s*' + pattern + r'($|\s)'
                    modified_prompt = re.sub(pattern_comma_before, r'\1', modified_prompt, flags=re.IGNORECASE)
                    # Case 4: word (handles item as the only thing in the prompt)
                    pattern_standalone = r'(^|\s)' + pattern + r'($|\s)'
                    modified_prompt = re.sub(pattern_standalone, r'\1\2', modified_prompt, flags=re.IGNORECASE)

                # Clean up any artifacts from removal, like double commas or extra spaces
                modified_prompt = re.sub(r'\s{2,}', ' ', modified_prompt).strip()
                modified_prompt = re.sub(r',(\s*,)+', ',', modified_prompt)
                modified_prompt = re.sub(r'\s+,', ',', modified_prompt)
                modified_prompt = re.sub(r',+\s*', ', ', modified_prompt)
                modified_prompt = modified_prompt.strip(' ,')

        # --- Addition ---
        if add_str:
            words_to_add = [word.strip() for word in add_str.split(',') if word.strip()]
            if words_to_add:
                print(f"  - Adding words: {words_to_add}")
                add_part = ", ".join(words_to_add)
                if modified_prompt: # Add comma only if prompt isn't empty
                    modified_prompt += ", " + add_part
                else:
                    modified_prompt = add_part

        print(f"  - Final Modified Prompt: '{modified_prompt[:100]}...'")
        return modified_prompt

    def after_component(self, component, **kwargs):
        """Capture references to the TARGET UI fields (prompt, seed, neg_prompt)."""
        elem_id = kwargs.get("elem_id")

        if elem_id == "img2img_prompt":
             self.prompt_input = component
             print(f"[Metadata Helper] Found target component reference: {elem_id}")
        elif elem_id == "img2img_neg_prompt":
             self.neg_prompt_input = component
             print(f"[Metadata Helper] Found target component reference: {elem_id}")
        elif elem_id == "img2img_seed":
             self.seed_input = component
             try:
                 if hasattr(component, 'interactive'): component.interactive = True
             except Exception as e:
                  print(f"[Metadata Helper Warning] Could not set seed input interactive: {e}")
             print(f"[Metadata Helper] Found target component reference: {elem_id}")

    def ui(self, is_img2img):
        print(f"[Metadata Helper] Creating UI (is_img2img={is_img2img})")
        if not is_img2img:
            return []

        accordion_component = InputAccordion if InputAccordion else gr.Accordion
        created_components = [] # Keep track of components created in this function

        with accordion_component(label=self.title(), open=False) as acc_instance:
            # 1. Hidden storage for the metadata dictionary
            self.hidden_metadata_store = gr.State({})
            # created_components.append(self.hidden_metadata_store) # State not usually returned

            # 2. PROXY Image Input Component
            with gr.Group():
                gr.Markdown("**Drop image here OR upload** to extract its metadata:")
                self.proxy_image_input = gr.Image(
                    label="Metadata Source Image", type="pil",
                    elem_id="metadata_helper_proxy_image", height=200,
                    interactive=True
                )
                created_components.append(self.proxy_image_input)

            # 3. Prompt Display and Modification Section
            with gr.Column():
                 # Textbox to display the extracted prompt (read-only)
                 self.display_extracted_prompt = gr.Textbox(
                     label="Extracted Prompt (read-only)",
                     interactive=False, # Make it read-only
                     lines=3,
                     elem_id="metadata_helper_display_prompt"
                 )
                 created_components.append(self.display_extracted_prompt)

                 # Textbox for words to remove
                 prompt_remove_words = gr.Textbox(
                     label="Remove words/phrases (comma-separated)",
                     #placeholder="e.g., blurry, low quality, watermark",
                     elem_id="metadata_helper_remove_words"
                 )
                 created_components.append(prompt_remove_words)

                 # Textbox for words to add
                 prompt_add_words = gr.Textbox(
                     label="Add words/phrases to end (comma-separated)",
                     #placeholder="e.g., 4k, masterpiece, high detail",
                     elem_id="metadata_helper_add_words"
                 )
                 created_components.append(prompt_add_words)


            # 4. Apply Buttons Row
            with gr.Row():
                send_seed_button = gr.Button("Apply Seed", variant="secondary")
                send_prompt_button = gr.Button("Apply Modified Prompt", variant="secondary") # Updated label
                send_neg_prompt_button = gr.Button("Apply Neg Prompt", variant="secondary")
                created_components.extend([send_seed_button, send_prompt_button, send_neg_prompt_button])


            # 5. Define Button Click Actions
            print(f"[Metadata Helper UI Check] Before binding button clicks:")
            print(f"  - prompt_input: {'OK' if self.prompt_input else 'MISSING'}")
            print(f"  - seed_input: {'OK' if self.seed_input else 'MISSING'}")
            print(f"  - neg_prompt_input: {'OK' if self.neg_prompt_input else 'MISSING'}")
            print(f"  - hidden_metadata_store: {'OK' if self.hidden_metadata_store else 'MISSING'}")
            print(f"  - proxy_image_input: {'OK' if self.proxy_image_input else 'MISSING'}")
            print(f"  - display_extracted_prompt: {'OK' if self.display_extracted_prompt else 'MISSING'}")

            # --- Helper function to get Seed/Neg Prompt (unchanged) ---
            def get_value_from_state(key, state_dict, current_value, target_type=None):
                if not isinstance(state_dict, dict):
                    gr.Warning(f"Metadata Helper: Stored data invalid. Upload image first.")
                    return current_value
                value = state_dict.get(key, None)
                if value is not None:
                    print(f"[Metadata Helper] Found '{key}' in stored metadata: '{str(value)[:100]}...'")
                    # Type conversion logic... (keep as before)
                    if target_type == int:
                        try: return int(float(value))
                        except (ValueError, TypeError):
                             gr.Warning(f"Metadata Helper: Could not parse '{key}' from metadata ('{value}').")
                             return current_value
                    elif target_type == float:
                        try: return float(value)
                        except (ValueError, TypeError):
                             gr.Warning(f"Metadata Helper: Could not parse '{key}' from metadata ('{value}').")
                             return current_value
                    elif target_type == str:
                         return str(value).strip()
                    else: return value
                else:
                    gr.Warning(f"Metadata Helper: '{key}' not found in metadata. Upload image first.")
                    return current_value

            # --- Bind button clicks ---
            # Seed Button (uses original helper)
            if self.seed_input and self.hidden_metadata_store:
                send_seed_button.click(
                    fn=lambda state, current: get_value_from_state("Seed", state, current, target_type=int),
                    inputs=[self.hidden_metadata_store, self.seed_input],
                    outputs=[self.seed_input], queue=False
                )
                print("[Metadata Helper] Seed button click bound.")
            else: print("[Metadata Helper WARNING] Seed button NOT bound - missing refs.")

            # Prompt Button (uses NEW helper)
            if self.prompt_input and self.hidden_metadata_store and prompt_remove_words and prompt_add_words:
                send_prompt_button.click(
                    fn=self._apply_modified_prompt, # Call the new function
                    # Inputs: State Dict, Remove String, Add String
                    inputs=[self.hidden_metadata_store, prompt_remove_words, prompt_add_words],
                    outputs=[self.prompt_input], # Output to the main prompt field
                    queue=False
                )
                print("[Metadata Helper] Modified Prompt button click bound.")
            else:
                 print("[Metadata Helper WARNING] Modified Prompt button NOT bound - missing component references.")
                 if not self.prompt_input: print("  - Missing: self.prompt_input")
                 if not self.hidden_metadata_store: print("  - Missing: self.hidden_metadata_store")
                 if not prompt_remove_words: print("  - Missing: prompt_remove_words")
                 if not prompt_add_words: print("  - Missing: prompt_add_words")


            # Negative Prompt Button (uses original helper)
            if self.neg_prompt_input and self.hidden_metadata_store:
                 send_neg_prompt_button.click(
                    fn=lambda state, current: get_value_from_state("Negative prompt", state, current, target_type=str),
                    inputs=[self.hidden_metadata_store, self.neg_prompt_input],
                    outputs=[self.neg_prompt_input], queue=False
                 )
                 print("[Metadata Helper] Negative Prompt button click bound.")
            else: print("[Metadata Helper WARNING] Negative Prompt button NOT bound - missing refs.")


            # Update outputs to include the display_extracted_prompt textbox
            if self.proxy_image_input and self.hidden_metadata_store and self.display_extracted_prompt:
                self.proxy_image_input.change(
                    fn=self.on_proxy_image_change,
                    inputs=[self.proxy_image_input],
                    # Outputs: [State Store, Display Textbox]
                    outputs=[self.hidden_metadata_store, self.display_extracted_prompt]
                )
                print("[Metadata Helper] Bound change event for proxy image component -> state & display.")
            else:
                print("[Metadata Helper WARNING] Proxy image component change event NOT bound (missing component refs).")


        # Return the list of components created in this function's scope
        # Or just the accordion instance if using InputAccordion
        if InputAccordion:
             return [acc_instance]
        else:
             return created_components


# --- Keep the on_app_started callback ---
def on_app_started(demo: gr.Blocks, app: FastAPI):
    print("[Metadata Helper] Extension script loaded (Proxy Image with Prompt Modify approach).")

script_callbacks.on_app_started(on_app_started)