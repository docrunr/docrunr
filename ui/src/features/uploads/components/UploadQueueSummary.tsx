import { Alert, Group, Text } from '@mantine/core';
import { useTranslation } from 'react-i18next';

type UploadQueueSummaryProps = {
  queueLength: number;
  isProcessing: boolean;
  batchTotal: number;
  currentIndex: number;
  successCount: number;
  failCount: number;
  requestError: string | null;
};

export function UploadQueueSummary({
  queueLength,
  isProcessing,
  batchTotal,
  currentIndex,
  successCount,
  failCount,
  requestError,
}: UploadQueueSummaryProps) {
  const { t } = useTranslation();

  const showLastBatch = !isProcessing && queueLength === 0 && (successCount > 0 || failCount > 0);

  return (
    <Group gap="md" wrap="wrap" align="flex-start" justify="space-between">
      <Group gap="xs" wrap="wrap">
        {isProcessing ? (
          <>
            <Text size="sm" c="dimmed">
              {t('upload.processingProgress', { current: currentIndex, total: batchTotal })}
            </Text>
            <Text size="sm" c="dimmed">
              {t('upload.countRemaining', { count: queueLength })}
            </Text>
            {failCount > 0 ? (
              <Text size="sm" c="red">
                {t('upload.countFailed', { count: failCount })}
              </Text>
            ) : null}
          </>
        ) : null}

        {!isProcessing && queueLength > 0 ? (
          <Text size="sm" c="dimmed">
            {t('upload.countSelected', { count: queueLength })}
          </Text>
        ) : null}

        {showLastBatch ? (
          <Text size="sm" c="dimmed">
            {t('upload.lastBatchSummary', { success: successCount, failed: failCount })}
          </Text>
        ) : null}
      </Group>

      {requestError ? (
        <Alert color="red" variant="light" py={4} px="sm" style={{ flex: '1 1 200px' }}>
          <Text size="xs">{requestError}</Text>
        </Alert>
      ) : null}
    </Group>
  );
}
