import { ActionIcon, Alert, Box, Button, Group, Modal, Paper, Stack, Text } from '@mantine/core';
import { IconInfoCircle, IconPlaylistAdd, IconTrash } from '@tabler/icons-react';
import { useTranslation } from 'react-i18next';
import { useDocumentUpload } from '../hooks/useDocumentUpload';
import { UploadDropzone } from './UploadDropzone';
import { UploadQueueSummary } from './UploadQueueSummary';

type UploadModalProps = {
  opened: boolean;
  onClose: () => void;
};

export function UploadModal({ opened, onClose }: UploadModalProps) {
  const { t } = useTranslation();
  const {
    queue,
    isProcessing,
    batchTotal,
    currentIndex,
    successCount,
    failCount,
    error,
    addFiles,
    removeFile,
    clearQueue,
    reset,
    submit,
  } = useDocumentUpload();

  const handleClose = () => {
    reset();
    onClose();
  };

  const locked = isProcessing;
  const hasQueue = queue.length > 0;

  return (
    <Modal
      opened={opened}
      onClose={handleClose}
      title={t('upload.title')}
      size={560}
      transitionProps={{ duration: 0 }}
      styles={{
        content: {
          display: 'flex',
          flexDirection: 'column',
          width: 'min(100%, 560px)',
          maxHeight: 'min(90vh, 720px)',
        },
        body: {
          display: 'flex',
          flexDirection: 'column',
          minHeight: 0,
          ...(hasQueue ? { flex: 1 } : {}),
        },
      }}
    >
      <Stack gap="md" style={hasQueue ? { flex: 1, minHeight: 0 } : undefined}>
        <Alert
          variant="light"
          color="gray"
          title={t('upload.workerAlertTitle')}
          icon={<IconInfoCircle />}
        >
          {t('upload.workerAlert')}
        </Alert>

        <Paper
          withBorder
          radius="md"
          p={queue.length === 0 ? 'sm' : 'md'}
          style={
            queue.length === 0
              ? { flex: '0 0 auto' }
              : {
                  flex: 1,
                  minHeight: 0,
                  display: 'flex',
                  flexDirection: 'column',
                  overflow: 'hidden',
                }
          }
        >
          {queue.length === 0 ? (
            <Stack gap="xs">
              <UploadDropzone onFilesSelected={addFiles} disabled={locked} />
              <Text size="sm" c="dimmed">
                {t('upload.noFilesHint')}
              </Text>
            </Stack>
          ) : (
            <Stack gap="md" style={{ flex: 1, minHeight: 0 }}>
              <Group justify="space-between" wrap="nowrap" gap="sm" flex="0 0 auto">
                <Text size="sm" fw={600} style={{ minWidth: 0 }} truncate>
                  {t('upload.queueCountLabel', { count: queue.length })}
                </Text>
                <Button
                  variant="subtle"
                  color="gray"
                  size="xs"
                  leftSection={<IconTrash size={14} />}
                  onClick={clearQueue}
                  disabled={locked}
                >
                  {t('upload.clearSelection')}
                </Button>
              </Group>

              <Box
                style={{
                  flex: 1,
                  minHeight: 0,
                  maxHeight: 280,
                  overflowY: 'auto',
                  overflowX: 'hidden',
                  overscrollBehavior: 'contain',
                }}
              >
                <Stack gap={6} pr={4}>
                  {queue.map((p) => (
                    <Group key={p.id} justify="space-between" wrap="nowrap" gap="sm">
                      <Text size="sm" style={{ flex: 1, minWidth: 0 }} truncate="end">
                        {p.file.name}
                      </Text>
                      <ActionIcon
                        variant="subtle"
                        color="gray"
                        size="sm"
                        aria-label={t('upload.remove')}
                        onClick={() => removeFile(p.id)}
                        disabled={locked}
                      >
                        <IconTrash size={16} />
                      </ActionIcon>
                    </Group>
                  ))}
                </Stack>
              </Box>

              <Button
                flex="0 0 auto"
                loading={locked}
                leftSection={<IconPlaylistAdd size={18} />}
                onClick={() => void submit()}
                disabled={!queue.length}
              >
                {t('upload.submit')}
              </Button>
            </Stack>
          )}
        </Paper>

        <UploadQueueSummary
          queueLength={queue.length}
          isProcessing={isProcessing}
          batchTotal={batchTotal}
          currentIndex={currentIndex}
          successCount={successCount}
          failCount={failCount}
          requestError={error}
        />
      </Stack>
    </Modal>
  );
}
