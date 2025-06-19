// Function to extract data, now RETURNS the data
async function getForgeCanvasData(targetElementId) {
    console.log(`[Metadata Helper JS File] >>> getForgeCanvasData CALLED for ID: ${targetElementId}`);
    const container = document.getElementById(`container_${targetElementId}`);
    let imageElement = null;
    let canvasElement = null;
    let base64Data = ''; // Default to empty string

    console.log(`[Metadata Helper JS File] Trying to find container: container_${targetElementId}`);
    if (container) {
        console.log(`[Metadata Helper JS File] Container found. Finding image/canvas elements...`);
        imageElement = container.querySelector(`img.forge-image`);
        canvasElement = container.querySelector(`canvas.forge-drawing-canvas`);
        console.log(`[Metadata Helper JS File] Found Elements - Image: ${imageElement ? 'Yes' : 'No'}, Canvas: ${canvasElement ? 'Yes' : 'No'}`);
    } else {
         console.log(`[Metadata Helper JS File] Container NOT found. Trying direct ID: ${targetElementId}`);
         const directElement = document.getElementById(targetElementId);
         if (directElement) {
              console.log(`[Metadata Helper JS File] Direct element found. Finding image/canvas elements...`);
              imageElement = directElement.querySelector(`img.forge-image`);
              canvasElement = directElement.querySelector(`canvas.forge-drawing-canvas`);
              console.log(`[Metadata Helper JS File] Found Elements - Image: ${imageElement ? 'Yes' : 'No'}, Canvas: ${canvasElement ? 'Yes' : 'No'}`);
         } else {
              console.warn(`[Metadata Helper JS File] Could not find element with ID: ${targetElementId}`);
         }
    }

    if (imageElement && imageElement.src && !imageElement.src.endsWith('/') && imageElement.naturalWidth > 0) {
        console.log(`[Metadata Helper JS File] Attempting extraction from image element src: ${imageElement.src.substring(0, 50)}...`);
        try {
            // Use a temporary canvas to get the data URL reliably
            const tempCanvas = document.createElement('canvas');
            tempCanvas.width = imageElement.naturalWidth;
            tempCanvas.height = imageElement.naturalHeight;
            const ctx = tempCanvas.getContext('2d');
            // Ensure the image is loaded before drawing, although for base64 src it might be immediate
            // A more robust approach might involve checking image.complete or using onload,
            // but for typical UI interaction this might suffice.
            ctx.drawImage(imageElement, 0, 0);
            base64Data = tempCanvas.toDataURL('image/png'); // Or appropriate type
            console.log(`[Metadata Helper JS File] Extracted base64 from image element (length: ${base64Data.length})`);
        } catch (e) {
            console.error(`[Metadata Helper JS File] Error drawing image to canvas: ${e}`);
            base64Data = ''; // Reset on error
        }
    }
    else if (canvasElement && (canvasElement.width > 1 || canvasElement.height > 1)) {
         console.log(`[Metadata Helper JS File] Attempting extraction from drawing canvas (size: ${canvasElement.width}x${canvasElement.height})`);
         try {
             base64Data = canvasElement.toDataURL('image/png');
             console.log(`[Metadata Helper JS File] Extracted base64 from drawing canvas (length: ${base64Data.length})`);
         } catch (e) {
              console.error(`[Metadata Helper JS File] Error getting data URL from canvas: ${e}`);
              base64Data = ''; // Reset on error
         }
    } else {
         console.warn(`[Metadata Helper JS File] No valid image source or canvas content found for ID: ${targetElementId}`);
         base64Data = ''; // Ensure empty string if nothing found
    }

    // --- REMOVED DOM Manipulation for hidden input ---
    // console.log(`[Metadata Helper JS File] Finding hidden input textarea with ID: img2img_metadata_helper_hidden_data`);
    // const hiddenInput = document.getElementById('img2img_metadata_helper_hidden_data')?.querySelector('textarea');
    // if (hiddenInput) { ... } else { ... }

    console.log(`[Metadata Helper JS File] <<< getForgeCanvasData FINISHED for ID: ${targetElementId} - Returning data length: ${base64Data.length}`);
    return base64Data; // Return the extracted data (or empty string)
}

// Function: Determines active tab and calls getForgeCanvasData, returns the result
async function getActiveImg2ImgMetadata() { // Made async to await getForgeCanvasData if needed, though it's synchronous now
    console.log("[Metadata Helper JS File] getActiveImg2ImgMetadata CALLED");
    const tabButtons = document.querySelectorAll('#mode_img2img .tabs > div > button');
    let activeTabIndex = 0;
    tabButtons.forEach((button, index) => {
        if (button.classList.contains('selected')) {
            activeTabIndex = index;
        }
    });
    console.log(`[Metadata Helper JS File] Active tab index found: ${activeTabIndex}`);

    const tabToElemId = {
        0: "img2img_image",      // img2img
        1: "img2img_sketch",     // Sketch
        2: "img2maskimg",        // Inpaint
        3: "inpaint_sketch",     // Inpaint sketch
        4: "img_inpaint_base",   // Inpaint upload
        5: null                  // Batch
    };

    const targetElementId = tabToElemId[activeTabIndex];
    let resultData = ''; // Default result

    if (targetElementId) {
        console.log(`[Metadata Helper JS File] Target element ID: ${targetElementId}`);
        // Call getForgeCanvasData and store its return value
        // Use await if getForgeCanvasData becomes truly async in the future
        resultData = await getForgeCanvasData(targetElementId);
    } else {
        console.warn(`[Metadata Helper JS File] No target element ID for active tab index ${activeTabIndex}. Returning empty string.`);
        resultData = '';
    }

    console.log(`[Metadata Helper JS File] getActiveImg2ImgMetadata FINISHING - returning data length: ${resultData.length}`);
    return resultData; // Return the final data
}
