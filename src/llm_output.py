"""Output errors that can be recovered by reducing the source budget."""


class LLMOutputTruncatedError(ValueError):
    output_validation_error = True


def reject_truncated_output(reason):
    if str(reason or '').lower() in {'length', 'max_tokens', 'max_output_tokens'}:
        raise LLMOutputTruncatedError(
            'LLM output was truncated at its token limit; reduce the section size or increase the output budget')
