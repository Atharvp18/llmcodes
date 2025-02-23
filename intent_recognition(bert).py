# -*- coding: utf-8 -*-
"""Intent_Recognition(BERT).ipynb

Automatically generated by Colab.

Original file is located at
    https://colab.research.google.com/drive/1qG8hEmTMpqeLO7QrazN-F3uJRAk1ITpF
"""

pip install transformers

pip install seqeval

import json
import pickle
import time
import datetime
import random
import os
import csv

import numpy as np
import pandas as pd
from tqdm.notebook import tqdm
import torch
from torch.utils.data import TensorDataset, random_split
from torch.utils.data import DataLoader, RandomSampler, SequentialSampler
from transformers import BertTokenizer
from transformers import BertForSequenceClassification, AdamW, BertConfig
from transformers import get_linear_schedule_with_warmup
from seqeval.metrics import f1_score

import matplotlib.pyplot as plt

device = torch.device("cpu")

SEED_VAL = 42

random.seed(SEED_VAL)
np.random.seed(SEED_VAL)
torch.manual_seed(SEED_VAL);  # Semicolon prevents jupyter from displaying last line as output

# SNIPS_PATH = "drive/MyDrive/data/snips"
TRAIN_PATH = "/content/train.tsv"
VAL_PATH = "/content/dev.tsv"
TEST_PATH = "/content/test.tsv"
df = pd.read_csv(TEST_PATH,sep='\t')

def load_snips_file(file_path):
    list_pair =[]
    with open(file_path,'r',encoding="utf8") as f:
        for line in f:
            split_line = line.split('\t')
            pair = split_line[0],split_line[1]
            list_pair.append(pair)
    return list_pair

all_train_examples = load_snips_file(TRAIN_PATH)
valid_examples = load_snips_file(VAL_PATH)
test_examples = load_snips_file(TEST_PATH)

len(all_train_examples)

intents = np.unique(np.array(all_train_examples)[:,0]).tolist()

intent_labeltoid = {intents[i]: i  for i in range(len(intents))}
intent_labeltoid

#How many training examples are there for each intent?
intent_series = pd.Series(np.array(all_train_examples)[:,0])
intent_series.value_counts()

def create_mini_training_set(examples_per_intent):
    intent_array = np.array(all_train_examples)[:,0]
    mini_batch =[]
    for intent in intents:
        add = intent_array[intent_array==intent]
        shuffled_indicies=np.random.RandomState(seed=42).permutation(len(add))
        class_indicies=shuffled_indicies[:examples_per_intent]
        sampled_set = np.array(all_train_examples)[class_indicies]
        mini_batch.append(sampled_set)
    mini_batch = np.array(mini_batch)
    mini_set = mini_batch.transpose(1,0,2).reshape(-1,mini_batch.shape[2])
    return mini_set

import re
def get_pad_length():
    all_train_examples_sentences = np.array(all_train_examples)[:,1]
    word_length = []
    for sentence in all_train_examples_sentences:
        number_words = len(re.findall(r'\w+',sentence))
        word_length.append(number_words)
    return max(word_length)

PAD_LEN = get_pad_length()

INTENT_DIM = 7

"""## BERT Tokenizer

"""

tokenizer = BertTokenizer.from_pretrained('bert-base-uncased', do_lower_case=True)

test_utterance = "Show statutes citing AIR 2012 SC 890"

print(tokenizer.encode_plus(
            test_utterance, add_special_tokens=True, max_length=PAD_LEN, pad_to_max_length=True,
            truncation=True, return_attention_mask=True, return_tensors='pt'
    ))

def examples_to_dataset(examples):
    input_ids = []
    attention_masks = []
    labels = []
    for instance in examples:
        token_dict = tokenizer.encode_plus(
                instance[1], add_special_tokens=True, max_length=PAD_LEN, pad_to_max_length=True,
                truncation=True, return_attention_mask=True, return_tensors='pt')
        input_ids.append(token_dict['input_ids'])
        attention_masks.append(token_dict['attention_mask'])
        labels.append(torch.tensor(intent_labeltoid[instance[0]]).type(torch.LongTensor))

    input_ids = torch.cat(input_ids)
    attention_masks = torch.cat(attention_masks)
    labels = torch.stack(labels)


    dataset = TensorDataset(input_ids, attention_masks, labels)

    return dataset

#prepare the validation/test dataloaders
val_dataset = examples_to_dataset(valid_examples)
test_dataset = examples_to_dataset(test_examples)
BATCH_SIZE = 2
validation_dataloader = DataLoader(val_dataset, sampler=RandomSampler(val_dataset), batch_size=BATCH_SIZE)
test_dataloader = DataLoader(test_dataset, sampler=SequentialSampler(test_dataset), batch_size=BATCH_SIZE)

def get_accuracy(preds, labels):
    pred_convd = np.argmax(preds,1).flatten()
    labels_flat = labels.flatten()
    correct_labels = np.equal(pred_convd,labels_flat).sum()
    accuracy_value = correct_labels/len(labels)
    return accuracy_value

# Quick tests for the implementation of accuracy.

preds1 = np.array([[1,2,3], [1,3,2], [3,2,1]])

assert get_accuracy(preds1, np.array([2,1,0])) == 1.0
assert get_accuracy(preds1, np.array([2,2,0])) == 2/3
assert get_accuracy(preds1, np.array([3,2,1])) == 0.0

count=0
for batch in tqdm(list(test_dataloader)):
    a,b,c= batch[0],batch[1],batch[2]
    count+=1
    if count ==1:
        break
print(a);print(b);print(c)
print(batch)
print(len(list(test_dataloader)))

import torch
import numpy as np
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score
from tqdm import tqdm

def evaluate(model, dataloader):
    model.eval()

    accuracy = []
    all_predictions = []
    all_true_labels = []

    for batch in tqdm(list(dataloader)):
        b_input_ids, b_input_mask, b_labels = batch

        with torch.no_grad():
            (loss, logits) = model(b_input_ids,
                                   token_type_ids=None,
                                   attention_mask=b_input_mask,
                                   labels=b_labels, return_dict=False)

        # Move logits and labels to CPU
        logits = logits.detach().cpu().numpy()
        label_ids = b_labels.to('cpu').numpy()

        # Calculate batch accuracy and store it
        batch_accuracy = get_accuracy(logits, label_ids)
        accuracy.append(batch_accuracy)

        # Get predicted labels by taking the argmax of the logits
        predictions = np.argmax(logits, axis=1)

        # Store all predictions and true labels for precision, recall, F1 calculation
        all_predictions.extend(predictions)
        all_true_labels.extend(label_ids)

    # Compute final accuracy
    avg_accuracy = np.mean(accuracy)
    print("Validation Accuracy: {}".format(avg_accuracy))

    # Compute precision, recall, F1 score using sklearn
    precision = precision_score(all_true_labels, all_predictions, average='weighted')
    recall = recall_score(all_true_labels, all_predictions, average='weighted')
    f1 = f1_score(all_true_labels, all_predictions, average='weighted')

    print(f"Accuracy: {avg_accuracy:.4f}")
    print(f"Precision: {precision:.4f}")
    print(f"Recall: {recall:.4f}")
    print(f"F1 Score: {f1:.4f}")

    return avg_accuracy, precision, recall, f1

def train(model, dataloader, epochs):
    optimizer = AdamW(model.parameters(), lr=2e-5, eps=1e-8)
    total_steps = len(train_dataloader) * epochs
    scheduler = get_linear_schedule_with_warmup(optimizer, num_warmup_steps=0, num_training_steps=total_steps)

    for epoch_i in range(0, EPOCHS):
        print('======== Epoch {:} / {:} ========'.format(epoch_i + 1, epochs))

        model.train()
        #n_iteration = 0
        accuracy = []
        total_train_loss = []

        for step, batch in tqdm(list(enumerate(train_dataloader))):
            # get input IDs, input mask, and labels from batch
            b_input_ids,b_input_mask,b_labels = batch

            model.zero_grad()
            #pass inputs through model
            (loss, logits) = model(b_input_ids,
                                   token_type_ids=None,
                                   attention_mask=b_input_mask,
                                   labels=b_labels, return_dict=False)
            logits = logits.detach().cpu().numpy()
            label_ids = b_labels.to('cpu').numpy()

            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimizer.step()
            scheduler.step()
            # Add to total_train_loss
            total_train_loss.append(loss)
            #logit_probability =torch.nn.Softmax(logits)
            batch_accuracy = get_accuracy(logits, label_ids)
            accuracy.append(batch_accuracy)
            #n_iteration += 1
        # Compute average train loss
        new_loss = [x.cpu().detach().numpy() for x in total_train_loss]
        avg_train_loss = np.mean(new_loss)
        print("  Average training loss: {0:.2f}".format(avg_train_loss))
        print("  Average Training accuracy: {0:.2f}".format(np.mean(accuracy)))
    #validation_accuracy =evaluate(bert_model, validation_dataloader)

BATCH_SIZE = 16

EPOCHS = 5
EXAMPLES_PER_INTENT = 2

mini_train_set = examples_to_dataset(create_mini_training_set(EXAMPLES_PER_INTENT))

train_dataloader = DataLoader(mini_train_set, sampler=RandomSampler(mini_train_set), batch_size=BATCH_SIZE)

bert_model = BertForSequenceClassification.from_pretrained(
    "bert-base-uncased", # Use the 12-layer BERT model, with an uncased vocab.
    num_labels = INTENT_DIM,
    output_attentions = False, # Whether the model returns attentions weights.
    output_hidden_states = False, # Whether the model returns all hidden-states.
)

train(bert_model, train_dataloader, EPOCHS)

print("Evaluating on test set:")
print("Test Scores:")
evaluate(bert_model, test_dataloader)