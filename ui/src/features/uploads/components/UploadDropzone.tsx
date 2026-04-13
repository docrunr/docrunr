import { Button, Stack, Text } from '@mantine/core';
import { IconUpload } from '@tabler/icons-react';
import { useRef } from 'react';
import { useTranslation } from 'react-i18next';

type UploadDropzoneProps = {
  onFilesSelected: (files: File[]) => void;
  disabled?: boolean;
};

export function UploadDropzone({ onFilesSelected, disabled = false }: UploadDropzoneProps) {
  const { t } = useTranslation();
  const inputRef = useRef<HTMLInputElement>(null);

  const pickFiles = (list: FileList | null) => {
    if (!list?.length) {
      return;
    }
    onFilesSelected(Array.from(list));
  };

  return (
    <Stack gap="sm">
      <input
        ref={inputRef}
        type="file"
        multiple
        hidden
        disabled={disabled}
        onChange={(e) => {
          pickFiles(e.currentTarget.files);
          e.currentTarget.value = '';
        }}
      />
      <div
        role="button"
        tabIndex={0}
        aria-label={t('upload.dropzoneAria')}
        onKeyDown={(e) => {
          if (disabled) {
            return;
          }
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault();
            inputRef.current?.click();
          }
        }}
        onDragOver={(e) => {
          if (disabled) {
            return;
          }
          e.preventDefault();
          e.stopPropagation();
        }}
        onDrop={(e) => {
          if (disabled) {
            return;
          }
          e.preventDefault();
          e.stopPropagation();
          pickFiles(e.dataTransfer.files);
        }}
        onClick={() => {
          if (!disabled) {
            inputRef.current?.click();
          }
        }}
        style={{
          border: '2px dashed var(--mantine-color-default-border)',
          borderRadius: 'var(--mantine-radius-md)',
          padding: 'var(--mantine-spacing-xl)',
          textAlign: 'center',
          cursor: disabled ? 'not-allowed' : 'pointer',
          opacity: disabled ? 0.6 : 1,
          background: 'var(--mantine-color-body)',
        }}
      >
        <Text size="sm" c="dimmed">
          {t('upload.dropOrClick')}
        </Text>
      </div>
      <Button
        fullWidth
        leftSection={<IconUpload size={18} />}
        disabled={disabled}
        onClick={() => inputRef.current?.click()}
      >
        {t('upload.firstStepUpload')}
      </Button>
    </Stack>
  );
}
