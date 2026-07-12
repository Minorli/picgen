const MIN_ABSOLUTE_SCORE_IMPROVEMENT = 2
const MIN_RELATIVE_SCORE_IMPROVEMENT = 0.25
const OFFICIAL_LOGO_MATCH_MIN_ALPHA = 245
const OFFICIAL_LOGO_MATCH_MAX_CHANNEL_DELTA = 24
// Upstream down/upscaling can shift intact logo edges by a few pixels.
const OFFICIAL_LOGO_MATCH_RADIUS = 3

const SAFETY_PADDING = Object.freeze({
  left: 0.12,
  top: 0.20,
  right: 0.50,
  bottom: 1,
})

function toPositiveInteger(value) {
  return Math.max(1, Math.floor(Number(value) || 0))
}

function normalizeRegion(ctx, region) {
  const canvasWidth = toPositiveInteger(ctx.canvas.width)
  const canvasHeight = toPositiveInteger(ctx.canvas.height)
  const x = Math.min(canvasWidth - 1, Math.max(0, Math.floor(Number(region.x) || 0)))
  const y = Math.min(canvasHeight - 1, Math.max(0, Math.floor(Number(region.y) || 0)))
  return {
    x,
    y,
    width: Math.max(1, Math.min(canvasWidth - x, Math.floor(Number(region.width) || 0))),
    height: Math.max(1, Math.min(canvasHeight - y, Math.floor(Number(region.height) || 0))),
  }
}

function pixelLuminance(data, index) {
  return 0.2126 * data[index] + 0.7152 * data[index + 1] + 0.0722 * data[index + 2]
}

function imageDataDimensions(imageData, pixelCount) {
  const width = Math.floor(Number(imageData?.width) || 0)
  const height = Math.floor(Number(imageData?.height) || 0)
  return width > 0 && height > 0 && width * height === pixelCount
    ? { width, height }
    : { width: pixelCount, height: 1 }
}

function hasNearbyLogoPixelMatch(base, logo, logoIndex, x, y, width, height) {
  for (let offsetY = -OFFICIAL_LOGO_MATCH_RADIUS; offsetY <= OFFICIAL_LOGO_MATCH_RADIUS; offsetY += 1) {
    const candidateY = y + offsetY
    if (candidateY < 0 || candidateY >= height) {
      continue
    }
    for (let offsetX = -OFFICIAL_LOGO_MATCH_RADIUS; offsetX <= OFFICIAL_LOGO_MATCH_RADIUS; offsetX += 1) {
      const candidateX = x + offsetX
      if (candidateX < 0 || candidateX >= width) {
        continue
      }
      const baseIndex = (candidateY * width + candidateX) * 4
      const largestChannelDelta = Math.max(
        Math.abs(base[baseIndex] - logo[logoIndex]),
        Math.abs(base[baseIndex + 1] - logo[logoIndex + 1]),
        Math.abs(base[baseIndex + 2] - logo[logoIndex + 2]),
      )
      if (largestChannelDelta <= OFFICIAL_LOGO_MATCH_MAX_CHANNEL_DELTA) {
        return true
      }
    }
  }
  return false
}

export function calculateOfficialLogoPixelMatch(baseImageData, logoImageData) {
  const base = baseImageData?.data
  const logo = logoImageData?.data
  if (!base || !logo || base.length !== logo.length || base.length % 4 !== 0) {
    return { score: 0, matchedPixels: 0, comparedPixels: 0 }
  }
  const pixelCount = logo.length / 4
  const { width, height } = imageDataDimensions(logoImageData, pixelCount)

  let matchedPixels = 0
  let comparedPixels = 0
  for (let index = 0; index < logo.length; index += 4) {
    if (logo[index + 3] < OFFICIAL_LOGO_MATCH_MIN_ALPHA) {
      continue
    }
    comparedPixels += 1
    const pixel = index / 4
    const x = pixel % width
    const y = Math.floor(pixel / width)
    if (hasNearbyLogoPixelMatch(base, logo, index, x, y, width, height)) {
      matchedPixels += 1
    }
  }

  return {
    score: comparedPixels ? matchedPixels / comparedPixels : 0,
    matchedPixels,
    comparedPixels,
  }
}

function analyzeRegion(ctx, region) {
  const { x, y, width, height } = normalizeRegion(ctx, region)
  const { data } = ctx.getImageData(x, y, width, height)
  let edgeTotal = 0
  let edgeCount = 0
  let denseEdgeCount = 0
  let textLikeEdgeCount = 0

  for (let py = 0; py < height; py += 1) {
    for (let px = 0; px < width; px += 1) {
      const index = (py * width + px) * 4
      const luminance = pixelLuminance(data, index)
      let hasDenseEdge = false
      let hasTextLikeEdge = false

      if (px + 1 < width) {
        const rightEdge = Math.abs(luminance - pixelLuminance(data, index + 4))
        edgeTotal += rightEdge
        edgeCount += 1
        hasDenseEdge ||= rightEdge >= 22
        hasTextLikeEdge ||= rightEdge >= 36
      }
      if (py + 1 < height) {
        const bottomEdge = Math.abs(luminance - pixelLuminance(data, index + width * 4))
        edgeTotal += bottomEdge
        edgeCount += 1
        hasDenseEdge ||= bottomEdge >= 22
        hasTextLikeEdge ||= bottomEdge >= 36
      }
      if (hasDenseEdge) {
        denseEdgeCount += 1
      }
      if (hasTextLikeEdge) {
        textLikeEdgeCount += 1
      }
    }
  }

  const pixelCount = Math.max(1, width * height)
  const averageEdge = edgeCount ? edgeTotal / edgeCount / 255 : 0
  const edgeDensity = denseEdgeCount / pixelCount
  const textLikeDensity = textLikeEdgeCount / pixelCount
  return {
    complexity: averageEdge * 100,
    penalty: averageEdge * 25 + edgeDensity * 30 + textLikeDensity * 45,
  }
}

export function expandLogoSafetyRegion(canvasWidth, canvasHeight, placement) {
  const safeCanvasWidth = toPositiveInteger(canvasWidth)
  const safeCanvasHeight = toPositiveInteger(canvasHeight)
  const width = toPositiveInteger(placement.width)
  const height = toPositiveInteger(placement.height)
  const placementX = Math.min(
    safeCanvasWidth - 1,
    Math.max(0, Math.floor(Number(placement.x) || 0)),
  )
  const placementY = Math.min(
    safeCanvasHeight - 1,
    Math.max(0, Math.floor(Number(placement.y) || 0)),
  )
  const left = Math.max(0, placementX - Math.round(width * SAFETY_PADDING.left))
  const top = Math.max(0, placementY - Math.round(height * SAFETY_PADDING.top))
  const right = Math.min(
    safeCanvasWidth,
    placementX + width + Math.round(width * SAFETY_PADDING.right),
  )
  const bottom = Math.min(
    safeCanvasHeight,
    placementY + height + Math.round(height * SAFETY_PADDING.bottom),
  )

  return {
    x: left,
    y: top,
    width: Math.max(1, right - left),
    height: Math.max(1, bottom - top),
  }
}

export function calculateRegionComplexity(ctx, region) {
  return analyzeRegion(ctx, region).complexity
}

export function calculateRegionTextEdgePenalty(ctx, region) {
  return analyzeRegion(ctx, region).penalty
}

export function calculateLogoPlacementScore(ctx, canvas, placement) {
  const safetyRegion = expandLogoSafetyRegion(canvas.width, canvas.height, placement)
  const coreAnalysis = analyzeRegion(ctx, placement)
  const safetyAnalysis = analyzeRegion(ctx, safetyRegion)
  return coreAnalysis.penalty * 0.55
    + safetyAnalysis.penalty * 0.35
    + safetyAnalysis.complexity * 0.10
}

export function chooseLogoPlacement(scoredCandidates) {
  if (!Array.isArray(scoredCandidates) || scoredCandidates.length === 0) {
    return null
  }

  const baseline = scoredCandidates[0]
  const alternatives = scoredCandidates.slice(1)
  const bestAlternative = alternatives.reduce((best, candidate) => {
    if (!Number.isFinite(candidate.score)) {
      return best
    }
    return !best || candidate.score < best.score ? candidate : best
  }, null)

  if (!Number.isFinite(baseline.score) || !bestAlternative) {
    return { ...baseline.placement }
  }

  const absoluteImprovement = baseline.score - bestAlternative.score
  const relativeImprovement = absoluteImprovement / Math.max(Math.abs(baseline.score), 1)
  const shouldMove = absoluteImprovement >= MIN_ABSOLUTE_SCORE_IMPROVEMENT
    && relativeImprovement >= MIN_RELATIVE_SCORE_IMPROVEMENT

  return { ...(shouldMove ? bestAlternative.placement : baseline.placement) }
}
