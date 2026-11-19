using System;
using Mazandasht.Domain;

namespace Mazandasht.Application
{
    /// <summary>Effective weighing parameters captured at registration time.</summary>
    public sealed class WeighParameters
    {
        public Weight DefaultBasketTare { get; set; }   // P01 (needs owner confirmation)
        public decimal LossPercent { get; set; }        // P02 (needs owner confirmation)
        public string SnapshotJson { get; set; } = "";
    }

    /// <summary>
    /// Weigh-ticket registration (Spec ch. 5.1): Net = Gross - Tare - Loss.
    /// Tare can come from basket count x per-basket tare. The effective
    /// parameters are snapshotted onto the ticket for traceability.
    /// </summary>
    public static class WeighTicketService
    {
        public static WeighTicket Register(WeighTicket ticket, WeighParameters parameters,
                                           Weight? explicitTare = null, Weight? explicitLoss = null)
        {
            if (ticket == null) throw new ArgumentNullException(nameof(ticket));
            if (parameters == null) throw new ArgumentNullException(nameof(parameters));

            var tare = explicitTare ?? SettlementCalculator.TareFromBaskets(
                ticket.BasketCount, parameters.DefaultBasketTare);
            var loss = explicitLoss ?? SettlementCalculator.LossFromPercent(
                ticket.Gross, parameters.LossPercent);

            ticket.Tare = tare;
            ticket.Loss = loss;
            ticket.Net = SettlementCalculator.NetWeight(ticket.Gross, tare, loss);
            ticket.ParamSnapshot = parameters.SnapshotJson;
            ticket.Status = DocumentStatus.Draft;
            return ticket;
        }
    }
}
