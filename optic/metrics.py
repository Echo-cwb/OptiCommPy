"""Metrics for signal and performance characterization."""
import numpy as np
from numba import njit
from scipy.special import erf
from optic.modulation import demodulateGray, GrayMapping
from optic.dsp import pnorm


@njit
def signal_power(x):
    """
    Calculate the average power of x.

    Parameters
    ----------
    x : np.array
        Signal.

    Returns
    -------
    scalar
        Average signal power of x: P = mean(abs(x)**2).

    """
    return np.mean(x * np.conj(x)).real


@njit
def hardDecision(rxSymb, constSymb, bitMap):
    """
    Minimum Euclidean distance based symbol decision.

    Parameters
    ----------
    rxSymb : TYPE
        received symbol sequence.
    constSymb : (M, 1) np.array
        Constellation symbols.
    bitMap : (M, log2(M)) np.array
        bit-to-symbol mapping.

    Returns
    -------
    decBits : np.array
        Sequence of decided bits.

    """
    M = len(constSymb)
    b = int(np.log2(M))

    decBits = np.zeros(len(rxSymb) * b)

    for i in range(len(rxSymb)):
        indSymb = np.argmin(np.abs(rxSymb[i] - constSymb))
        decBits[i * b: i * b + b] = bitMap[indSymb, :]
    return decBits


def fastBERcalc(rx, tx, M, constType):
    """
    Monte Carlo BER/SER/SNR calculation.

    Parameters
    ----------
    rx : np.array
        Received symbol sequence.
    tx : np.array
        Transmitted symbol sequence.
    M : int
        Modulation order.
    constType : string
        Modulation type: 'qam' or 'psk'.

    Returns
    -------
    BER : np.array
        Bit-error-rate.
    SER : np.array
        Symbol-error-rate.
    SNR : np.array
        Estimated SNR from the received constellation.

    """
    # constellation parameters
    constSymb = GrayMapping(M, constType)
    Es = np.mean(np.abs(constSymb) ** 2)

    # We want all the signal sequences to be disposed in columns:
    try:
        if rx.shape[1] > rx.shape[0]:
            rx = rx.T
    except IndexError:
        rx = rx.reshape(len(rx), 1)
    try:
        if tx.shape[1] > tx.shape[0]:
            tx = tx.T
    except IndexError:
        tx = tx.reshape(len(tx), 1)
    nModes = int(tx.shape[1])  # number of sinal modes
    SNR = np.zeros(nModes)
    BER = np.zeros(nModes)
    SER = np.zeros(nModes)

    # get bit mapping
    b = int(np.log2(M))
    bitMap = demodulateGray(constSymb, M, constType)
    bitMap = bitMap.reshape(-1, b)

    # pre-processing
    for k in range(nModes):
        # symbol normalization
        rx[:, k] = pnorm(rx[:, k])  # / np.sqrt(signal_power(rx[:, k]))
        tx[:, k] = pnorm(tx[:, k])  # / np.sqrt(signal_power(tx[:, k]))

        # correct (possible) phase ambiguity
        rot = np.mean(tx[:, k] / rx[:, k])
        rx[:, k] = rot * rx[:, k]

        # estimate SNR of the received constellation
        SNR[k] = 10 * np.log10(
            signal_power(tx[:, k]) / signal_power(rx[:, k] - tx[:, k])
        )
    for k in range(nModes):
        # hard decision demodulation of the received symbols
        brx = hardDecision(np.sqrt(Es) * rx[:, k], constSymb, bitMap)
        btx = hardDecision(np.sqrt(Es) * tx[:, k], constSymb, bitMap)

        err = np.logical_xor(brx, btx)
        BER[k] = np.mean(err)
        SER[k] = np.mean(np.sum(err.reshape(-1, b), axis=1) > 0)
    return BER, SER, SNR


@njit
def calcLLR(rxSymb, σ2, constSymb, bitMap):
    """
    LLR calculation (circular AGWN channel).

    Parameters
    ----------
    rxSymb : np.array
        Received symbol sequence.
    σ2 : scalar
        Noise variance.
    constSymb : (M, 1) np.array
        Constellation symbols.
    bitMap : (M, log2(M)) np.array
        Bit-to-symbol mapping.

    Returns
    -------
    LLRs : np.array
        sequence of calculated LLRs.

    """
    M = len(constSymb)
    b = int(np.log2(M))

    LLRs = np.zeros(len(rxSymb) * b)

    for i in range(len(rxSymb)):
        prob = np.exp((-np.abs(rxSymb[i] - constSymb) ** 2) / σ2)

        for indBit in range(b):
            p0 = np.sum(prob[bitMap[:, indBit] == 0])
            p1 = np.sum(prob[bitMap[:, indBit] == 1])

            LLRs[i * b + indBit] = np.log(p0) - np.log(p1)
    return LLRs


def monteCarloGMI(rx, tx, M, constType):
    """
    Monte Carlo based generalized mutual information (GMI) estimation.

    Parameters
    ----------
    rx : np.array
        Received symbol sequence.
    tx : np.array
        Transmitted symbol sequence.
    M : int
        Modulation order.
    constType : string
        Modulation type: 'qam' or 'psk'

    Returns
    -------
    GMI : np.array
        Generalized mutual information values.
    MIperBitPosition : np.array
        Mutual information per bit position.

    """
    # constellation parameters
    constSymb = GrayMapping(M, constType)
    Es = np.mean(np.abs(constSymb) ** 2)

    # We want all the signal sequences to be disposed in columns:
    try:
        if rx.shape[1] > rx.shape[0]:
            rx = rx.T
    except IndexError:
        rx = rx.reshape(len(rx), 1)
    try:
        if tx.shape[1] > tx.shape[0]:
            tx = tx.T
    except IndexError:
        tx = tx.reshape(len(tx), 1)
    nModes = int(tx.shape[1])  # number of sinal modes
    GMI = np.zeros(nModes)

    noiseVar = np.var(rx - tx, axis=0)

    # get bit mapping
    b = int(np.log2(M))
    bitMap = demodulateGray(constSymb, M, constType)
    bitMap = bitMap.reshape(-1, b)

    # symbol normalization
    for k in range(nModes):
        # symbol normalization
        rx[:, k] = pnorm(rx[:, k])  # / np.sqrt(signal_power(rx[:, k]))
        tx[:, k] = pnorm(tx[:, k])  # / np.sqrt(signal_power(tx[:, k]))

        # correct (possible) phase ambiguity
        rot = np.mean(tx[:, k] / rx[:, k])
        rx[:, k] = rot * rx[:, k]
    for k in range(nModes):
        # set the noise variance
        σ2 = noiseVar[k]

        # hard decision demodulation of the transmitted symbols
        btx = hardDecision(np.sqrt(Es) * tx[:, k], constSymb, bitMap)

        # soft demodulation of the received symbols
        LLRs = calcLLR(rx[:, k], σ2, constSymb / np.sqrt(Es), bitMap)

        # LLR clipping
        LLRs[LLRs == np.inf] = 500
        LLRs[LLRs == -np.inf] = -500

        # Compute bitwise MIs and their sum
        b = int(np.log2(M))

        MIperBitPosition = np.zeros(b)

        for n in range(b):
            MIperBitPosition[n] = 1 - np.mean(
                np.log2(1 + np.exp((2 * btx[n::b] - 1) * LLRs[n::b]))
            )
        GMI[k] = np.sum(MIperBitPosition)
    return GMI, MIperBitPosition


def monteCarloMI(rx, tx, M, constType, px=[]):
    """
    Monte Carlo based mutual information (MI) estimation.

    Parameters
    ----------
    rx : np.array
        Received symbol sequence.
    tx : np.array
        Transmitted symbol sequence.
    M : int
        Modulation order.
    constType : string
        Modulation type: 'qam' or 'psk'
    pX : (M, 1) np.array
        p.m.f. of the constellation symbols. The default is [].

    Returns
    -------
    MI : np.array
        Estimated MI values.

    """
    if len(px) == 0:  # if px is not defined
        px = 1 / M * np.ones(M)  # assume uniform distribution
    # constellation parameters
    constSymb = GrayMapping(M, constType)
    Es = np.sum(np.abs(constSymb) ** 2 * px)
    constSymb = constSymb / np.sqrt(Es)

    # We want all the signal sequences to be disposed in columns:
    try:
        if rx.shape[1] > rx.shape[0]:
            rx = rx.T
    except IndexError:
        rx = rx.reshape(len(rx), 1)
    try:
        if tx.shape[1] > tx.shape[0]:
            tx = tx.T
    except IndexError:
        tx = tx.reshape(len(tx), 1)
    nModes = int(rx.shape[1])  # number of sinal modes
    MI = np.zeros(nModes)

    for k in range(nModes):
        # symbol normalization
        rx[:, k] = pnorm(rx[:, k])  # / np.sqrt(signal_power(rx[:, k]))
        tx[:, k] = pnorm(tx[:, k])  # / np.sqrt(signal_power(tx[:, k]))

    # Estimate noise variance from the data
    noiseVar = np.var(rx - tx, axis=0)

    for k in range(nModes):
        σ2 = noiseVar[k]
        MI[k] = calcMI(rx[:, k], tx[:, k], σ2, constSymb, px)
    return MI


@njit
def calcMI(rx, tx, σ2, constSymb, pX):
    """
    Mutual information (MI) calculation (circular AGWN channel).

    Parameters
    ----------
    rx : np.array
        Received symbol sequence.
    tx : np.array
        Transmitted symbol sequence.
    σ2 : scalar
        Noise variance.
    constSymb : (M, 1) np.array
        Constellation symbols.
    pX : (M, 1) np.array
        prob. mass function (p.m.f.) of the constellation symbols.

    Returns
    -------
    scalar
        Estimated mutual information.

    """
    N = len(rx)
    H_XgY = np.zeros(1, dtype=np.float64)
    H_X = np.sum(-pX * np.log2(pX))

    for k in range(N):
        indSymb = np.argmin(np.abs(tx[k] - constSymb))

        log2_pYgX = (
            -(1 / σ2) * np.abs(rx[k] - tx[k]) ** 2 * np.log2(np.exp(1))
        )  # log2 p(Y|X)
        # print('pYgX:', pYgX)
        pXY = (
            np.exp(-(1 / σ2) * np.abs(rx[k] - constSymb) ** 2) * pX
        )  # p(Y,X) = p(Y|X)*p(X)
        # print('pXY:', pXY)
        # p(X|Y) = p(Y|X)*p(X)/p(Y), where p(Y) = sum(q(Y|X)*p(X)) in X

        pY = np.sum(pXY)

        # print('pY:', pY)
        H_XgY -= log2_pYgX + np.log2(pX[indSymb]) - np.log2(pY)
    H_XgY = H_XgY / N

    return H_X - H_XgY


def Qfunc(x):
    return 0.5 - 0.5 * erf(x / np.sqrt(2))


def theoryBER(M, EbN0, constType):
    """
    Theoretical (approx.) bit error probability for QAM/PSK in AWGN channel.

    Parameters
    ----------
    M : int
        Modulation order.
    EbN0 : scalar
        Signal-to-noise ratio (SNR) per bit in dB.
    constType : string
        Modulation type: 'qam' or 'psk'

    Returns
    -------
    Pb : scalar
        Theoretical probability of bit error.

    """
    EbN0lin = 10 ** (EbN0 / 10)
    k = np.log2(M)

    if constType == "qam":
        L = np.sqrt(M)
        Pb = (
            2
            * (1 - 1 / L)
            / np.log2(L)
            * Qfunc(np.sqrt(3 * np.log2(L) / (L ** 2 - 1) * (2 * EbN0lin)))
        )
    elif constType == "psk":
        Ps = 2 * Qfunc(np.sqrt(2 * k * EbN0lin) * np.sin(np.pi / M))
        Pb = Ps / k
    return Pb
