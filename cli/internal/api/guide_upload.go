package api

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"encoding/json/jsontext"
	"errors"
	"io"
	"mime"
	"net/http"
	"net/url"
)

// MaxGuideDocumentBytes is ART's hard transfer ceiling, not the configured
// project/document allowance. Workstream may enforce a smaller limit.
const MaxGuideDocumentBytes = 512 * 1024 * 1024

type GuideUploadReceipt struct {
	DocumentID string `json:"document_id"`
	SHA256     string `json:"sha256"`
	ByteCount  int64  `json:"byte_count"`
	Status     string `json:"status"`
	Replayed   bool   `json:"replayed"`
}

// UploadGuideDocument sends the exact original once. Its receipt proves only
// stored bytes, not setup completion, policy approval or guide activation.
func (c *Client) UploadGuideDocument(ctx context.Context, project, guide, document string, source io.ReadSeeker, size int64, mediaType, key string) (Result[GuideUploadReceipt], error) {
	var result Result[GuideUploadReceipt]
	if !validUUID(project) || !validUUID(guide) || !validUUID(document) || !validUUID(key) ||
		len(project) > 100 || len(guide) > 100 || len(document) > 100 || len(key) > 100 || !guideMediaType(mediaType) {
		return result, errors.New("upload selectors and --idempotency-key must be UUIDs; use a declared guide media type")
	}
	if source == nil || size <= 0 || size > MaxGuideDocumentBytes {
		return result, errors.New("upload requires a nonempty bounded original")
	}
	digest := sha256.New()
	if _, err := source.Seek(0, io.SeekStart); err != nil {
		return result, errors.New("cannot read original")
	}
	count, err := io.Copy(digest, io.LimitReader(source, size+1))
	if err != nil || count != size {
		return result, errors.New("cannot read unchanged original")
	}
	expectedHash := "sha256:" + hex.EncodeToString(digest.Sum(nil))
	if _, err := source.Seek(0, io.SeekStart); err != nil {
		return result, errors.New("cannot rewind original")
	}
	path := "/api/v1/projects/" + url.PathEscape(project) + "/guides/" + url.PathEscape(guide) +
		"/documents/" + url.PathEscape(document) + "/content"
	response, err := c.openBodyRequest(ctx, c.guideHTTP, http.MethodPost, path, "",
		io.LimitReader(source, size), size, key, "application/json", mediaType)
	if err != nil {
		return result, guideUploadFailure(err)
	}
	defer response.Body.Close()
	raw, err := io.ReadAll(io.LimitReader(response.Body, maxResponseBytes+1))
	invalid := &Failure{Code: "invalid_api_response", Status: response.StatusCode, OutcomeUnknown: true}
	if err != nil || len(raw) > maxResponseBytes {
		return result, guideUploadFailure(invalid)
	}
	if response.StatusCode != http.StatusAccepted {
		return result, guideUploadFailure(c.responseFailure(http.MethodPost, response, raw))
	}
	responseType, _, err := mime.ParseMediaType(response.Header.Get("Content-Type"))
	if err != nil || responseType != "application/json" || !jsontext.Value(raw).IsValid() ||
		response.Header.Get("Content-Encoding") != "" && response.Header.Get("Content-Encoding") != "identity" {
		return result, guideUploadFailure(invalid)
	}
	var value GuideUploadReceipt
	_, err = contextObject(json.RawMessage(raw), &value,
		[]string{"document_id", "sha256", "byte_count", "status", "replayed"}, nil)
	if err != nil || !sameUUID(value.DocumentID, document) || value.SHA256 != expectedHash || value.ByteCount != size || value.Status == "" {
		return result, guideUploadFailure(invalid)
	}
	if value.Status != "document_stored" && value.Status != "object_confirmed" {
		return result, guideUploadFailure(&Failure{Code: "guide_document_upload_unconfirmed", Status: response.StatusCode, OutcomeUnknown: true})
	}
	return Result[GuideUploadReceipt]{Raw: json.RawMessage(raw), Value: value}, nil
}

func guideUploadFailure(err error) error {
	var failure *Failure
	if errors.As(err, &failure) && failure.OutcomeUnknown {
		failure.RecoveryHint = "guide upload outcome unknown; replay only the unchanged selectors, original bytes, media type and idempotency key"
	}
	return err
}
