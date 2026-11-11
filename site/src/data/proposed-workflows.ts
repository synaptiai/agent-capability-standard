// Workflow ids a domain profile lists on purpose although no catalog defines
// them yet. The domain pages show these as proposed, with no link. Any other
// id a profile lists that no catalog defines fails the build, so a renamed
// workflow or a typo is caught instead of being shown as a proposal. When a
// catalog defines one of these, or the profile drops it, remove it here.
export const PROPOSED_WORKFLOWS: Readonly<Record<string, readonly string[]>> = {
  audio: ['speech_recognition_pipeline', 'audio_classification_pipeline', 'speaker_verification', 'audio_quality_assessment'],
  multimodal: ['image_captioning_pipeline', 'visual_question_answering', 'text_to_image_generation', 'cross_modal_search'],
  vision: ['image_classification_pipeline', 'object_detection_pipeline', 'visual_quality_inspection', 'image_generation_review'],
};
